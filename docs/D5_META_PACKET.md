# Д5 — метаданные не приезжают (okna, 27.08)

Продолжение блокера свежести после Д4 (`docs/D4_PIPELINE_BROKEN.md`).
Такт доходит до init/precheck OK и останавливается: нет снимка `$metadata`.

## 1. Что лежит в приёмнике `[замер 27.08 ~13:12 UTC]`

| Метка | Число |
|---|---|
| Пакеты в `inbox/okna-1` | **74** |
| `kind=delta` | **74** |
| `kind=full` | **0** |
| `kind=meta` | **0** |
| `metadata.included=true` | **0** |
| `metadata.included=false` | **74** |
| Срок | **2026-08-24T05:37:25Z** … **2026-08-27T08:00:39Z** |
| Файл `/var/lib/serenedb/packet-meta/okna-1/$metadata` | **нет** (только `skipped.json` + `.first-data`) |
| `journalctl 1c-packet-apply` «metadata записан» с 20.08 | **0** |
| Агент в логе | **1.0.2** (репозиторий — **1.1.3** после Д5) |
| Контур в `bases.json` | **704** entities, `config_version` был 3 → после сигнала **4** |

`1c-packet-server`: health OK; последний PUT пакета **000176** в 08:01;
далее только `GET /agent/config` (~каждые 20 мин). `1c-packet-apply`:
«verified нет — нечего применять». Таймер пайплайна остановлен на время
Д5 (иначе цикл fail раз в минуту).

Свежесть витрины/корпуса (не снято):

| k | v | смысл |
|---|---|---|
| `build_ts` | 1787550031 | ~24.08, конец такта |
| `corpus_built_ts` | 1787323074 | момент чтения витрины удачной сборкой |
| `mart_changed_ts` | 1787817782 | витрина новее (apply шёл) |

Предупреждение бота про возраст **не** снято: корпус не пересобран.

## 2. Кто кладёт снимок — факт, не догадка

Источник: `windows/packet-agent/src/PacketAgent.cs` + контракт
`docs/PACKET_CONTRACT.md` §5/§8/§9.

Агент кладёт чанк `metadata` и `metadata.included=true`, когда:

1. **первая заливка / resync** (`full_done=false` или `resync`) — обязательно;
2. **отпечаток `$metadata` изменился** относительно `state.json` →
   `metadata_fingerprint`;
3. **контур пуст** и отпечаток ещё не совпал с локальным — `kind=meta`
   (починка тупика §3.64 HOW_NOT_TO);
4. **с 27.08 / 1.1.3:** `params.need_metadata=1` от приёмника — сразу
   `kind=meta`, даже если отпечаток совпал.

Иначе в обычном `delta` стоит **`metadata.included=false` — так задумано**:
снимок не дублируется каждый такт, только при смене схемы / first / запросе.

Почему у всех 74 пакетов `included=false`: агент уже считает снимок
доставленным (`metadata_fingerprint` в state), схема 1С не менялась,
контур непустой (704) — ветка `kind=meta` не срабатывает. Это **не**
дефект контракта delta; дефект — **нет обратного канала**, когда файл на
Ubuntu пропал (или никогда не был записан apply: с 20.08 «metadata
записан» = 0 на этой коробке).

## 3. Что починено (код)

| Файл | Изменение |
|---|---|
| `ubuntu/packet/packet_meta_signal.py` | `request` / `ack` / `status`: флаг `params.need_metadata`, bump `config_version` |
| `ubuntu/serenedb/build.sh` | до precheck: нет `$GATE/$metadata` → `request` + **fail** с явным текстом |
| `ubuntu/packet/packet_apply.py` | после записи снимка — `ack_metadata` |
| `windows/packet-agent/…/PacketAgent.cs` | **1.1.3**: читает `need_metadata`, шлёт `kind=meta` до обхода контура |
| `ubuntu/packet/deploy_packet.sh` | в FILES добавлен `packet_meta_signal.py` |
| `docs/PACKET_CONTRACT.md` §8 | описан `params.need_metadata` |
| `ubuntu/packet/test_packet_meta_signal.py` | замок **PASS 20 FAIL 0** |

На okna выкатано: `build.sh`, `packet_apply.py`, `packet_meta_signal.py`;
в `bases.json` выставлен `need_metadata=1`, `config_version=4`; в env
добавлен `PACKET_BASE_ID=okna-1`.

`serene_ask.py` **не** трогали (чужой исполнитель). Полный
`deploy-okna-serene-ask.sh` не гоняли: в дереве изменён чужой ask — гейт
HEAD не совпал бы; выкат точечный.

## 4. Замок — живой прогон

```text
meta-signal: okna-1: need_metadata уже выставлен, config_version=4 …
СБОРКА ПРЕРВАНА: нет снимка $metadata в /var/lib/serenedb/packet-meta/okna-1
  (база okna-1) — агенту выставлен need_metadata=1; ждать kind=meta
  (агент ≥1.1.3) или на Windows: packet-agent.exe --smoke
is-active: failed
```

Раньше падение было в `corpus_build.sql`: «сущностей 0». Теперь — **до**
корпуса, с инструкцией. Оффлайн: `python3 ubuntu/packet/test_packet_meta_signal.py`
→ **20/0**.

## 5. Почему такт до конца СЕЙЧАС не доходит — одно действие

Обратный канал работает только на **агенте ≥1.1.3**. Живой okna шлёт
`agent_version=1.0.2` — флаг `need_metadata` он **игнорирует** (параметры
читает только `page_size` / `tact_seconds` / `chunk_mb`).

Прямого SSH/RDP/WinRM к Windows с этой стороны нет (`docs/RUNBOOK_DEPLOY.md`,
`docs/NETWORK.md`). Бэкапа `$metadata` на Ubuntu нет.

**Одно действие на машине Windows с агентом okna:**

```text
C:\1c\packet\packet-agent.exe --smoke
```

(при занятом демоне — сначала остановить задачу «1C Packet Agent», затем
`--smoke`, затем вернуть задачу; см. HOW_NOT_TO §3.63/§3.64).

Альтернатива на ту же машину: `upgrade-agent.cmd` (подтянет exe ≥1.1.3 с
S3 **после** публикации сборки 1.1.3) — тогда `need_metadata=1` уже
выставлен, агент сам пришлёт `kind=meta` на ближайшем такте без `--smoke`.

После появления файла `$metadata`: apply снимет флаг; `systemctl start
1c-serene-pipeline@postgres.timer` — такт должен пройти корпус. Пока
таймер **остановлен** (`inactive`), чтобы не крутить fail.

## 6. Автономность после апгрейда агента

На чужой базе с агентом ≥1.1.3 путь без человека:

1. пропал / нет `$metadata` → `build.sh` → `packet_meta_signal request`;
2. агент на такте видит `need_metadata` → `kind=meta`;
3. apply пишет файл → `ack`;
4. следующий такт собирает корпус.

Пока на окне 1.0.2 — шаг 2 не исполняется без действия из §5.
