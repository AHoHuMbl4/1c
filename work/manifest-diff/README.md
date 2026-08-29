# manifest-diff — калибровка генератора синтетического $metadata

Инструментарий этапа 3 установщика v2 (11.08): сверка синтетического `$metadata`
(генератор `windows/odata-setup/src/manifest-gen.ps1`, обход метаданных через COM)
против живого `$metadata` публикации OData.

## Файлы

- `diff_metadata.py` — сверка двух XML: flatten обоих до строк
  `EntityType/Property: имя, тип, nullable` и diff. Известные расхождения
  подключаются файлом исключений (`known-exceptions-ut11.txt` — формат: одна
  строка-правило на расхождение, с причиной).
- `PHASE3-STATE.md` — полный отчёт этапа 3: дефект-кейсы, вердикты K1–K7,
  ловушки стенда, эталонные sha256 сборок.
- `diff-final.txt` — итоговый diff по УТ 11 после калибровки (пустой за
  исключениями = MATCH 2836/2836 сущностей).
- `diff-iter*.txt`, `gen-log.txt` — промежуточные итерации калибровки (в git не
  лежат, рабочие файлы).
- `gen_metadata_vitrine.py` — генератор из витрины SereneDB (`duckdb_columns` +
  список сущностей OData); без COM/Windows. Замок: `test_gen_metadata_vitrine.py`.
- `run-metadata-okna.sh` — прогон для okna на машине с витриной `127.0.0.1:7890`.
- `metadata-okna.xml` — артефакт контура okna (819 сущностей из
  `docs/completeness-okna/contour.txt`, **7633** свойств в генераторе / 819
  EntitySet). **Перегенерировать на живой витрине
  окна** (`bash work/manifest-diff/run-metadata-okna.sh`); установка в
  `/var/lib/serenedb/packet-meta/okna-1/` — оркестратор, не этот скрипт.
- `remote-gen-okna-once.sh` — scp фикса + прогон на `gpu-erw` `/tmp/genrepo`.

## Парсер такта (corpus_build.sql §1)

Движок читает `$metadata` через `read_text(gate/'$metadata')` и разбирает regex:

| Шаг | Что извлекает |
|---|---|
| `tmp3_ent` | `<EntityType …>…</EntityType>` → `entity` (lower), `body` |
| `tmp3_prop` | `<Property Name="…" Type="…"` → prop, edm |
| `tmp3_key` | `<Key><PropertyRef Name="…"/>` → key_cols; для Recorder+LineNumber в витрине — дополняет ключ |
| §1-бис | `accumulationregister_%_recordtype` + prop `RecordType` → `balance_registers` |
| §1-тер | формы balance_map: RecordType-тени, accounting (AccountDr/Cr), warehouse (Edm numeric + Period) |
| §1-кватер | informationregister + DateTime≠Period + Guid*_Key + numeric + chartofcharacteristictypes |
| §1-quint | catalog (ref_key/code/description), курсы IR, document/accumulation facts с currency-ref |

Генератор `gen_metadata_vitrine.py` выдаёт ту же форму: EntityType/EntitySet,
ключи по платформенным именам (`Ref_Key`, `Recorder`/`Recorder_Type`,
`LineNumber`, `RecordType`), Edm-типы по `duckdb_columns()` и имени колонки.

## Как повторить калибровку на другой базе

1. Снять живой `$metadata`: `GET <публикация>/odata/standard.odata/$metadata`
   под пользователем-читателем → `live-metadata-<база>.xml`.
2. Сгенерировать синтетический: прогон установщика (мягкий шаг после шага 12)
   или `manifest-gen.ps1` напрямую с env `OC1C_PROGID`/`OC1C_CONNSTR`/
   `OC1C_MANIFEST_OUT` → `gen-metadata-<база>.xml`.
   **Без Windows:** `python3 work/manifest-diff/gen_metadata_vitrine.py --dsn …
   --entities-file contour.txt --out metadata-<база>.xml` (витрина SereneDB).
3. `python3 diff_metadata.py live.xml gen.xml` — расхождения либо в
   исключения с причиной, либо в правку генератора.

Большие XML и дампы `tox/` в git не кладутся (`.gitignore`): это мегабайты
производных данных, воспроизводимых двумя командами выше.

## Открытый вопрос (находка снайпера коммита 11.08)

Порог маппинга целых чисел (`numT16 = 4`: ≤4 разрядов → `Edm.Int16`, иначе
`Edm.Int64`) подтверждён калибровкой на одной конфигурации (УТ 11, 65
уникальных описаний типов) и утверждением «`Edm.Int32` платформа 8.3.27 в типах
свойств не использует». Снайпер коммита требует подтверждения границы на второй
независимой конфигурации. Порог переопределяется env `OC1C_NUM_T16` без правки
кода. До подтверждения умолчание — по калибровке УТ (K4: flatten 3/3
байт-в-байт).
