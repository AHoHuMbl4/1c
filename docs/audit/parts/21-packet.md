# 21. packet

## Зачем участок нужен
Транспорт витрины 1С с Windows на Ubuntu: агент читает OData, пакует CSV-чанки (zstd±age) и шлёт HTTP на приёмник; приёмник принимает и проверяет пакеты; apply заливает verified-пакеты в SereneDB; config-builder считает контур сущностей для агента и пишет его в файл баз.

## Входы
- **Агент** (`PacketAgent.cs`): `agent.ini` — `base_id`, `receiver_url`, `token`, `recipient_pubkey` (опц.), `odata_url`/`odata_user`/`odata_password`, `data_dir`, `metadata_file` (опц.), `client_cert_thumbprint`, `page_size`/`page_min`/`tact_seconds`/`chunk_mb`/`batch_mb`/`batch_seconds`/`progress_seconds`/`log_dir` (Cfg.Load:84-134). CLI: без аргументов — демон; `--smoke`, `--send-log <path>`, `--flatten …`, `--version` (Main:3052+).
- **Приёмник** (`packet_server.py`): тело PUT manifest/chunk; query `base_id` у config/progress; заголовки `Authorization: Bearer …`, опц. `X-SSL-Client-CN` (385-403). Файл баз `PACKET_BASES` — JSON `{base_id: {token, identity, config}}` (86-102, 124-136).
- **Apply** (`packet_apply.py`): каталог `PACKET_ROOT/inbox/<base>/<pkg>/` со `state.json`=`verified` и `manifest.json`; `--base` / `PACKET_APPLY_BASE`, `--dry-run` / `PACKET_APPLY_DRY_RUN` (915-922).
- **Config** (`packet_config.py`): argv `base_id`; `--dsn`, `--bases`, `--dry-run` (440-447). Читает `base_profile`, опц. `search_entity_force`/`search_entity_class`, файл `$metadata` (273-291).

## Порядок работы
1. **Агент-демон**: mutex → цикл тактов `Tact.Run` (3145-3180). Сначала довозка `queue/*` (`ResumePackage`, 1970-1993).
2. `GET /v1/agent/config` → контур/`params`/`recipient_pubkey` или снимок `config.json` (1996-2045). Пустой контур + неподтверждённый fingerprint → пакет `kind=meta` с `$metadata` (2049-2087).
3. `$metadata` (HTTP или `metadata_file`) → обход `entities`: индекс/проба версий → `delta`/`gone_only`/`full`/`full_entity` (`ProcessEntity` 2259-2364); `FlushEntity` пишет чанки на диск (1902-1931).
4. Порция при `batch_mb`/`batch_seconds` или финал: `SendPackage` → манифест±age → `UploadAndFinish`: PUT manifest → опрос status → PUT missing chunks → при `verified`/`applied` обновление индекса и снятие очереди (2405-2747).
5. **Приёмник**: PUT manifest → decrypt (age) или plain JSON → validate → `receiving` (499-559); PUT chunk по sha/bytes (561-595); GET status при полном наборе чанков → `_verify_package` (sha→age→zstd→sha) → `verified` (623-640).
6. **Apply** (таймер/CLI): `_iter_verified` по `seq` (882-912) → decrypt/zstd → entities (`full`/`full_entity` CREATE; `delta` TEMP+DELETE+INSERT) → gone → metadata/skipped/log файлы → `_contract_tx` → `_mark_applied` (783-877). Сбой базы: `skip_bases`, поздние пакеты той базы не идут (941-951).
7. **Config**: SQL-контур → `compute_contour` (+only_binary по `$metadata`) → атомарно `PACKET_BASES.config` (+`config_version`) и `search_entity_skipped` (336-437).

## Выходы
- Приёмник → диск: `inbox/<base>/<pkg>/{manifest,*.zst[.age],state.json}`, `inbox/<base>/{state.json,progress.json}` (server 8-15, 459-464).
- Apply → SereneDB: таблицы сущностей, `search_changed_sources`, `base_profile`, `search_quality`; файлы `PACKET_META_DIR/<base>/$metadata`, `skipped.json`, `logs/`, `.first-data` (596-636, 711-762).
- Config → `PACKET_BASES[].config.entities/params/config_version` (агент читает GET config); `search_entity_skipped` (414-436).
- Агент → локально: `data_dir/{state.json,config.json,queue/,index/,cache/}`; журнал.

## Обращения наружу
| Место | Что | Назначение |
|---|---|---|
| Agent `OData` ~918+ | HTTP Basic к `odata_url` | страницы/ключи/`$metadata` 1С |
| Agent `Receiver` 1634-1689 | HTTPS+mTLS+Bearer к приёмнику | config, progress, manifest, chunk, status |
| Agent 1849/1859 | `zstd.exe`, `age.exe` | сжатие/шифрование |
| Server 311,316 | `age` decrypt, `zstd -d` | verify чанков |
| Apply `_psql*` 175-197 | `psql SERENEDB_DSN` | DDL/DML витрины, счётчики |
| Apply 231-237 | age/zstd | открытие чанков |
| Config `_rows`/`_exec` 112-127 | `psql` | контур, skipped |
| Config 285-288 | чтение файла `$metadata` | only_binary / бутстреп EntitySet |
| `packet_crypto` | `age`/`age-keygen` CLI | encrypt/decrypt/recipient |
| `packet_kit` 107-112, 59-101 | `psql` SELECT base_profile; `openssl` | комплект базы (не боевой тракт данных) |

Вызовов языковой модели в участке нет.

## Переключатели
| Имя | Где | Умолчание |
|---|---|---|
| `PACKET_ROOT` | server:40, apply:33 | `/var/lib/1c-packet` |
| `PACKET_LISTEN` | server:41 | `127.0.0.1:6021` |
| `PACKET_BASES` | server/apply/config | `/etc/1c-packet-bases.json` |
| `PACKET_ZSTD_BIN` | server:43, apply:36 | `/usr/bin/zstd` |
| `PACKET_MAX_CHUNK_BYTES` | server:47 | 64 MiB |
| `PACKET_MAX_CHUNKS_PER_PACKAGE` | server:60 | `0` (без предела) |
| `PACKET_MAX_INBOX_BYTES` | server:61 | 20 GiB |
| `PACKET_MAX_ACTIVE_PACKAGES` | server:62 | 8 |
| `PACKET_MAX_PROGRESS_BYTES` | server:65 | 16384 |
| `SERENEDB_DSN` | apply:35, config:50 | `host=127.0.0.1 port=7890 …` |
| `PACKET_META_DIR` | apply:593, config:55 | `/var/lib/serenedb/packet-meta` |
| `PACKET_APPLY_CSV_MAX_LINE` | apply:40 | 200 MiB |
| `PACKET_APPLY_GONE_BATCH` | apply:42 | 1000 |
| `PACKET_APPLY_RO_ROLE` / `PACKET_CONFIG_RO_ROLE` | apply:46, config:67 | `serene_ro` |
| `PACKET_APPLY_THREADS` | apply:60-63 | `0` (не SET threads) |
| `PACKET_APPLY_BASE` / `PACKET_APPLY_DRY_RUN` | apply:917-920 | пусто / выкл. |
| `PACKET_CONFIG_PAGE_SIZE`/`TACT_SECONDS`/`CHUNK_MB` | config:60-62 | 10000 / 1200 / 32 |
| `PACKET_AGE_BIN` / `PACKET_AGE_KEYGEN_BIN` | crypto:19-20 | which |
| `PACKET_CA_KEY`/`CRT`, `PACKET_OPENSSL_BIN`, `PACKET_CLIENT_CERT_DAYS` | kit:36-40 | `/etc/1c-packet-ca.*`, 825 |
| Агент: пустой `recipient_pubkey` | Cfg:81-82, Tact:1783 | plain (только zstd) |

## Развилки
- **Auth**: нет базы/токена, CN≠base_id → 401 (server 391-403).
- **Manifest**: age / `{` plain / иначе `bad_format`; `stale_seq`, лимиты active/inbox → 409/429 (499-552).
- **Verify**: hash/decrypt/zstd/plain mismatch → `quarantined` (283-329).
- **Apply op**: `full`/`full_entity` vs `delta` vs skip не-`_DATA_OPS`; Quarantine (`mix_versions`, `delta_without_*`, `chunk_missing`) vs failed (остаётся verified) (812-864).
- **Config**: пустая перепись → бутстреп из EntitySet `$metadata` или FATAL (350-366); без изменений `config_version` не растёт (420-422).
- **Агент**: firstRun/`Resync` → full; индекс+версии → delta; empty contour → meta; режим age≠очереди → DropQueue (1978-1992); `stale_seq` → Seq+=1e6 + Resync (2752-2760).

## Чего здесь нет
- Нет чтения/записи 1С на запись; нет NL2SQL и вызовов LLM.
- Приёмник не заливает витрину (только до `verified`); apply не слушает HTTP.
- Нет фонового воркера verify — только синхронно в GET status (server 634-638).
- Агент не отбирает контур сам — список только с сервера (Tact 1996-2036; config docstring:1-7).
- `packet_kit` не вставляет запись в боевой `/etc` — пишет kit в `--out` (kit:173-178).
- Тесты (`test_packet_*.py`), shell/systemd юниты — вспомогательные; в тракт данных не входят.
