# Аудит T1-A4: row-level дельта такта («полная B»)

Дата: 02.09.2026. Режим: только чтение репозитория; серверы не трогались.
Якоря: `plan-takt-fix-v10.md`, `pipeline.sh`, `corpus_build.sql`, `corpus_merge.sql`,
`packet_apply.py`, `changed_sources_sql.py`, `FIX_PLAN_2026-09-02.md`.
Доки SereneDB: `sql/statements/merge_into` (через MCP `read_section`).

---

## Вердикт одной строкой

**B0 (инфраструктура списков) есть; полной B (row-level фильтр `p_doc` + безопасный
partial-DELETE в merge) нет.** Сборка по-прежнему entity-level через
`search_changed_sources` → `tmp3_build`. Таблица `search_changed_rows` пишется только
packet-`delta`/`gone`, **никем не читается**, `partial_rebuild=0` — мёртвая константа.
Узкое место монолита `document_реализациятмц` (~75k × широкая схема, dup-гейт / пустой
порядок ключей → без чанков) полной B как раз и адресуется — но ключ корпуса
(`sha1(doc)` / запрет смены формулы) и семантика DELETE при частичном `tmp3_corpus`
ещё не спроектированы до исполнимого контракта.

---

## 1. Как устроена сегодняшняя дельта

### 1.1. Кто пишет «что изменилось» (уровень сущности)

| Писатель | Что пишет | Гранулярность | Где |
|---|---|---|---|
| `packet_apply._contract_tx` | `search_changed_sources` (дописывание) + `changed_sources_ok=1` | таблица | `packet_apply.py:899-923` |
| `changed_sources_sql` (HTTP-синк) | wipe+INSERT списка прогона; packet — только append | таблица | `changed_sources_sql.py:13-31` |
| `pipeline.sh` KEEP_MARKS | снимок `tmp_changed_keep` до `serene_sync`, restore sources после | таблица | `pipeline.sh:49-62` |

Сборка решает «кого пересобирать» **только** по таблицам:

- инкремент включён, если `changed_sources_ok=1` ∧ корпус непуст ∧ `search_refmap` непуст
  (`corpus_build.sql:1004-1007`);
- `tmp3_changed` = пересечение `tmp3_src` ∩ `search_changed_sources`
  (`corpus_build.sql:1010-1013`);
- `tmp3_build` = полный проход **или** renamed>200 **или** changed **или** lag **или**
  дети lag-родителей **или** сущности, чьи `refs` содержат переименованное имя
  (`corpus_build.sql:1336-1347`);
- диспетчер: `EXECUTE p_doc` / `p_doc_chunk` / `p_doc_plain` **по каждой** таблице из
  `tmp3_build` целиком (`corpus_build.sql:2169-2227`).

**Почему всё равно по-сущностно:** ни один путь сборки не читает `search_changed_rows`.
Даже одна строка дельты → сущность в `search_changed_sources` → вся витрина сущности в
`p_doc`.

### 1.2. Кто пишет `search_changed_rows` (уровень строки) — B0

DDL (оба места, `IF NOT EXISTS`):

- `packet_apply._ensure_contract_tables` — `packet_apply.py:890-892`
- `pipeline.sh` до синка — `pipeline.sh:53`

**Писатель один: `packet_apply`.** Не синк HTTP, не `changed_sources_sql`, не
`serene_sync` (waiver v10: HTTP rows не пишет — `plan-takt-fix-v10.md:174`).

| op / путь | `key_text` | `op` | Код |
|---|---|---|---|
| `delta` | `string_agg` значений **витринных** `key_cols` через `\|` (порядок = `base_profile.key_props` ⊕ enrich `LineNumber` при `Recorder`, как `corpus_build.sql:61-65`; сопоставление имён `lower`) | `'delta'` | `packet_apply.py:578-618, 702-708` |
| `gone.csv` | `ref_key` **как шлёт агент** (часто один `Ref_Key` документа) | `'deleted_gone'` | `packet_apply.py:717-750` |
| `full` / `full_entity` | **не пишет rows** (только `changed_tables` → sources) | — | `packet_apply.py:998-1028` |

Инварианты ключа (спека B0):

- `key_text` = **витринный** ключ, **не** корпусный `row_key`, **не** `sha1(doc)` —
  apply не может вычислить doc (`plan-takt-fix-v10.md:73-79`);
- `DataVersion` в `key_text` **не входит** (DV — проверка mix-versions
  `packet_apply.py:621-635` и транспорт дельты 1С, не тождество строки корпуса);
- если `_resolve_key_cols` вернул пусто → блок INSERT rows **пропущен**
  (`if key_cols:` — `packet_apply.py:703`); ГИПОТЕЗА: сущности без `key_props`/manifest
  key копят только entity-отметку.

Форма DELETE витрины при delta (не путать с ключом корпуса):

- есть `Ref_Key` → `DELETE … WHERE Ref_Key IN (d_)` — **все строки документа** с этим
  Ref_Key снимаются и вставляются заново (`packet_apply.py:638-643, 683-693`);
- нет `Ref_Key` → EXISTS по `(Recorder, LineNumber[, Recorder_Type])`
  (`packet_apply.py:644-652`).

### 1.3. Полнота списка rows

| Вопрос | Факт |
|---|---|
| Все ли сущности? | Только те, что прошли packet `delta` с непустым `key_cols`, плюс `gone`. HTTP-синк — **0 rows** (waiver). `full_entity` — **0 rows**. |
| Все ли op? | Фактически `'delta'` и `'deleted_gone'`. Отдельного `'delete'` нет. |
| Потребление? | **Нет.** Merge: `\set partial_rebuild 0` + комментарий «копится» (`corpus_merge.sql:4-6`); `DELETE FROM search_changed_sources` есть (`:1003-1004`), `search_changed_rows` **не чистится**. |
| KEEP rows? | Снимок `tmp_changed_rows_keep` до sync есть (`pipeline.sh:55`); **restore после sync отсутствует** (в отличие от sources `:59-62`). Пока список никто не ест — поведение такта не ломает; для полной B — дыра (см. также `result-ta-a7.md`). Замок B0 проверяет только «снимок до sync» (`test_corpus_merge_key_form.py:198-202`). |

### 1.4. Связь с FIX_PLAN

`docs/audit/FIX_PLAN_2026-09-02.md` этап **6** — порядок **MERGE → APPLY xfer → DELETE** и
pending-страховка карты (`:162-177`), не row-level `p_doc`. «Полная B» в FIX_PLAN **не
входит**; она — waiver пакета v10 (`plan-takt-fix-v10.md:172-173`) и бэклог
`activeContext` (отдельный пакет после аудита). Этап 6 обязан быть **совместим** с
будущей B (дыра DELETE→xfer на авто-тактах — принятый долг до этапа 6).

---

## 2. Дизайн полной B (скелет)

Цель: при `src_table ∈ tmp3_build` собирать в `tmp3_corpus` **только** затронутые
витринные строки (+ корректно снять удалённые), не меняя семантику `row_key` /
`content_hash` существующих строк (`plan-takt-fix-v10.md:16-19`).

### 2.1. Инварианты

1. Формула корпусного `row_key` и `content_hash` **не меняется** (запрет rewrite ключей).
2. `key_text` остаётся витринным; стыковка витрина→корпус — **отдельный** шаг SQL.
3. `partial_rebuild=1` меняет семантику DELETE merge: анти-джойн «весь src_table из
   стейджа» (`corpus_merge.sql:887-890`) при частичном стейдже **снесут** неизменённые
   строки сущности — текущий DELETE при partial **запрещён без замены**.
4. Вектора не терять: неизменённые `row_key` в боевом корпусе **не трогать**; изменённые
   с новым `content_hash` → `emb=NULL` → bulk; карта xfer — для rewrite/сдвигов формы.
5. Потребление `search_changed_rows` — только после успешного merge, и только
   `src_table ∈ tmp3_build` (как sources сегодня).
6. Правило TARGET п.20: фильтр/merge/delete — **одним SQL внутри движка**; Python
   только доставляет дельту в витрину (уже делает apply).

### 2.2. Шаги (логическая машина)

```
B0 (есть)          → накопитель search_changed_rows
B1 снимок/restore  → KEEP+RESTORE rows симметрично sources (pipeline)
B2 материал. дельты→ tmp3_row_delta (src_table, key_text, op) ∩ tmp3_build
B3 expand витрины  → tmp3_row_mart_keys: витринные строки, попавшие под delta/gone
B4 фильтр p_doc    → p_doc / p_doc_chunk только по этим строкам → tmp3_corpus (partial)
B5 map→corpus keys → tmp3_row_corpus_keys (витринный key_text → множество row_key)
B6 merge partial   → MERGE стейджа; DELETE только по B5 ∪ gone-расширению
B7 consume         → DELETE search_changed_rows WHERE src_table ∈ tmp3_build
B8 gate            → сверка count сущности = было − deleted + inserted (не «стейдж=корпус»)
```

### 2.3. По какому ключу фильтровать витрину

| Класс сущности | Витринный фильтр | Почему |
|---|---|---|
| Регистр / набор с натуральным ключом (`Recorder`+`LineNumber`[+Type]) | `key_text` = склейка тех же колонок, что `_key_text_expr` / `tmp3_key` | Совпадает с корпусным `row_key` (string_agg key_cols) — прямое равенство часто возможно |
| Документ / fold `key_cols=['Ref_Key']` | фильтр по **`Ref_Key` ∈ key_text** (как gone уже задумано: «разрешает все строки витрины с этим Ref_Key» — `packet_apply.py:720-721`) | Delta уже переписывает **все** строки документа с этим Ref_Key (`_delta_delete_clause`); строка ТЧ ≠ объект дельты |
| `row_key = sha1(doc)` (fallback / пустой ключ / план по realiz) | фильтр витрины: по `Ref_Key` если колонка есть, иначе по полному натуральному ключу из `tmp3_key`; **не** по sha1 | sha1 вычислим только после сборки doc; apply его не пишет |
| `DataVersion` | **не** ключ фильтра корпуса | Меняется на объект; не различает строки ТЧ; не в `key_text` |

ГИПОТЕЗА по realiz (okna): ~75k строк корпуса ≈ витрина, ~8.3k документов; dup-гейт /
отсутствие чанков (`activeContext`, `plan-takt-fix-v10` A); `row_key=sha1(doc)` по
спеке v10. Значит «row-level» для неё на практике = **document-level** (все строки
витрины с затронутым Ref_Key), не «одна ячейка LineNumber», пока формула ключа
запрещена. Это всё равно кратное ускорение: N документов ≪ 75k.

### 2.4. Совмещение с чанкованием (A) и dup-гейтом

Текущее A (`corpus_build.sql:1382-1534`):

- порог `nrows×ncols > chunk_cells`; порции по `tmp3_pdoc_order.pos`;
- dup-гейт: `count(*)≠count(DISTINCT keyvals)` → сущность **монолит** (`:1522-1534`);
- пустой `key_cols` → не чанкуется (`:1439`).

При полной B:

| Случай | Поведение |
|---|---|
| Сущность чанкуемая, дельта мала | **Не строить** полный `tmp3_pdoc_order` на всю таблицу: материализовать order/фильтр **только** по `tmp3_row_mart_keys` (или один проход `WHERE key IN (…)`) — иначе «ускорение» сожрёт order-UNPIVOT |
| Dup-монолит (realiz) | Чанки A всё равно off; выигрыш = **фильтр источника** `p_doc`, не порции |
| Fold + surrogate в order | Order-ключ ≠ corpus `row_key`; фильтр дельты — по витринному `key_text`/`Ref_Key`, порции — по pos **внутри** отфильтрованного множества |
| Resume `tmp3_pdoc_progress` | При partial прогресс/формула должны быть scoped к «набору ключей такта» или partial **не** использует chunk-resume (проще: partial всегда monophase без resume) |

### 2.5. Удаления (`op=deleted_gone` / исчезнувшие строки)

Сегодня при entity-rebuild DELETE = «корпус src_table ∉ стейдж»
(`corpus_merge.sql:887-890`) — корректно, потому что стейдж полный по сущности.

При partial стейдже нужна **явная** модель:

1. **`deleted_gone`:** `key_text` = Ref_Key документа.
   - Если строки ещё можно увидеть — нет (уже DELETE из витрины).
   - Расширение: все **корпусные** `row_key`, ранее принадлежавшие этому Ref_Key.
   - Прямого поля «Ref_Key» в `search_corpus` нет; при fold/sha1 GUID может **не**
     входить в `doc` (`corpus_build.sql:1707` — Ref_Key+own_ref → NULL в тексте).
   - ГИПОТЕЗА вариантов закрытия (волна проверки выберет один):
     - (A) вспомогательная колонка/таблица `search_corpus_vkey(src_table,row_key,key_text)`
       пишется при сборке штатным SQL;
     - (B) для fold хранить в корпусе `row_key=Ref_Key` или `Ref_Key|…` — **запрещено**
       v10 для существующих строк;
     - (C) при gone по документу: `DELETE` всех corpus-строк сущности, чей бизнес-объект
       матчится через уже существующие эвристики merge (`split_part`, recorder-prefix) —
       хрупко для sha1;
     - (D) gone по документу → временно **entity-level** rebuild только этой таблицы
       (fallback), rows-partial — для delta-update.

2. **Строка исчезла без gone** (delta переписала документ без части LineNumber):
   после expand: `mart_keys_after` для Ref_Key; corpus keys этого объекта, которых нет в
   новом стейдже объекта → DELETE. Требует умения перечислить «старые keys объекта»
   (та же дыра, что п.1).

3. Штатный MERGE: доки прямо поддерживают `WHEN MATCHED THEN DELETE` и
   `WHEN NOT MATCHED BY SOURCE THEN DELETE` (`sql/statements/merge_into`). Последнее
   на полном USING=partial **эквивалентно сносу сущности** — для B **нельзя** без
   ограничения source/target предикатом «только кандидаты».

### 2.6. Таблицы (имена — рабочий скелет)

| Таблица | Содержание |
|---|---|
| `search_changed_rows` | уже есть: src_table, key_text, op, ts |
| `tmp3_row_delta` | distinct дельта ∩ tmp3_build |
| `tmp3_row_filter` | предикат/ключ для `query_table` / `p_doc` |
| `tmp3_corpus` | как сейчас, но только rebuilt rows |
| `tmp3_row_replaced` | row_key к удалению (gone ∪ старые ключи объекта) |
| `tmp3_merge_emb_xfer` | как сейчас; scope = rewrite wave **или** partial matched set |

Флаг: `\set partial_rebuild 1` реально ветвит DELETE/postcheck (сейчас переменная
декоративна — `corpus_merge.sql:6`, подтверждено `result-drev-2.md`).

---

## 3. Вектора при row-level дельте

### 3.1. Как работает сейчас (entity rebuild)

1. Карта `tmp3_merge_emb_*` / `tmp3_merge_emb_xfer` — стыковка по **уникальному**
   `content_hash` (и запасной путь refs+bmap) на rewrite-wave
   (`corpus_merge.sql:506-561`).
2. MERGE: при том же `(src_table,row_key)` и **том же** `content_hash` — ветка UPDATE
   не срабатывает (`… content_hash IS DISTINCT FROM …` — `:855`); emb остаётся.
3. При смене `content_hash`: UPDATE текста, `emb=NULL` unless `corpus_bmap_common_eq`
   (`:855`); затем xfer-UPDATE пакетами (`:900-915`); остальное — embed_bulk.
4. FIX_PLAN этап 6: переставить **APPLY xfer до DELETE**, pending-страховка карты —
   закрывает окно потери при mid-abort; полной B это **предпосылка**, не замена.

### 3.2. Целевое поведение при partial

| Строка | Действие | emb |
|---|---|---|
| Не в дельте, не в tmp3_build | Не читается merge | без изменений |
| В дельте, content_hash тот же | MERGE no-op / matched same hash | без пересчёта |
| В дельте, content_hash новый | UPDATE + emb NULL (+xfer если bmap/hash-map) | bulk только она |
| Gone / replaced key | DELETE после xfer (этап 6) | уходит с строкой |
| Новая строка | INSERT emb NULL | bulk |

Карта xfer при partial: строить по `src_table ∈ tmp3_build` **и** ключам стейджа (не
требует rewrite-wave ≥90%); уникальность content_hash в пределах сущности — тот же
инвариант, что сейчас (`HAVING count(*)=1`).

### 3.3. Оценка доли пересчёта на регулярном такте

**Не замер этого аудита (серверы закрыты).** Оценка по устройству:

- Доля **сущностей** в `tmp3_build` на спокойном такте обычно мала (дельта apply); внутри
  затронутой сущности сегодня p_doc гоняет **100%** строк витрины, а embed — лишь строки
  с новым content_hash / NULL (MERGE уже экономит деньги модели).
- Полная B режет прежде всего **CPU/wall p_doc** (монолит часов), не обязательно число
  `ai_embed`: на «1 документ из 8390» ожидаемо ~0.01–0.1% строк сущности в стейдже;
  пересчёт emb ≈ доля строк с реально изменившимся каноном doc.
- ГИПОТЕЗА: на такте «0 изменений» после consume sources уже минуты; после полной B тот
  же критерий обязан держаться и при «1 строка регистра» без часового p_doc.
- ГИПОТЕЗА риска: rename>200 или пустой/неполный rows → вынужденный полный проход;
  full_entity без rows → entity rebuild как сейчас.

---

## 4. Штатное vs «свой скрипт» (TARGET п.20)

### Штатно движком (допустимо и уже в духе кода)

- `CREATE TABLE` / temp / `CREATE OR REPLACE TABLE … AS SELECT`
- Фильтр витрины: `semi/anti join`, `WHERE EXISTS`, `IN (SELECT …)`
  (доки: `sql/query_syntax/from_and_join#semi-and-anti-joins`)
- `MERGE INTO … WHEN MATCHED / NOT MATCHED / MATCHED THEN DELETE`
  (доки: `sql/statements/merge_into` — upsert и delete-set)
- `UPDATE … FROM` для xfer emb (уже `:909-915`)
- `DELETE … WHERE NOT EXISTS` с **явным** списком кандидатов
- Макросы `corpus_content_hash` / bmap (уже в merge)
- Потребление отметок одним `DELETE FROM search_changed_rows WHERE …`

### Уже погранично, но принято проектом как контур доставки (не «обработка корпуса»)

- `packet_apply.py`: CSV → TEMP `d_*` → DELETE/INSERT витрины + INSERT списка
  одним SQL-шаблоном (`:709-714`) — аналог OData-доставки, не вычисление корпуса снаружи.

### Запрещено п.20 (не делать в полной B)

- Вычитать корпус/витрину в Python, фильтровать, писать обратно;
- `psql` в цикле по ключам/сущностям для сборки текста/хешей;
- Свой UNPIVOT/эмбеддинг вне `ai_embed` / SQL-макросов;
- Менять `row_key` «чтобы было удобнее джойнить» (запрет v10 + потеря emb).

Граница: **решение «какие ключи трогать»** формируется в SQL из
`search_changed_rows`+витрины; Python максимум дополняет контракт apply (как B0).

---

## 5. Что уже есть / чего не хватает (чеклист)

| Компонент | Статус | Доказательство |
|---|---|---|
| Таблица `search_changed_rows` DDL | есть (scaffolding) | `packet_apply.py:890-892`, `pipeline.sh:53` |
| Запись delta key_text | есть | `packet_apply.py:702-708` |
| Запись gone | есть (Ref_Key-уровень) | `packet_apply.py:748-750` |
| Снимок rows до sync | есть | `pipeline.sh:55` |
| Restore rows после sync | **нет** | `pipeline.sh:59-62` только sources |
| HTTP пишет rows | **нет** (waiver) | `plan-takt-fix-v10.md:174` |
| full_entity пишет rows | **нет** | `packet_apply.py:1008-1028` |
| Чтение rows в build/merge | **нет** | grep: только DDL/комментарии |
| `partial_rebuild` ветвление | **нет** (константа 0) | `corpus_merge.sql:4-6` |
| Фильтр p_doc по ключам | **нет** | диспетчер `tmp3_build` целиком `:2172-2227` |
| Partial-safe DELETE | **нет** | entity anti-join `:887-890` |
| Map key_text→row_key (sha1/fold) | **нет** | — |
| Consume rows после merge | **нет** | только sources `:1003-1004` |
| Совместимость с этапом 6 FIX_PLAN (xfer→DELETE) | план есть, код этапа 6 ещё нет | `FIX_PLAN:162-167`; сейчас DELETE затем xfer `:887-915` |
| Замки B0 | есть | `test_corpus_merge_key_form.py:176-202`, `test_corpus_merge_gone_register.py` |
| Замки полной B / partial | **нет** | — |

---

## 6. Открытые вопросы (волна проверки)

### По коду / живому окну (без правок; один read-only psql на окне — **отдельное
разрешение владельца**; этот аудит SSH не делал)

1. Живая схема `search_changed_rows`: есть ли колонка `ts`? (ранее probe: 3 col без ts —
   `result-drev-2.md` / `result-tf8-2.md`; `IF NOT EXISTS` не мигрирует).
2. Сколько строк в `search_changed_rows` после реальных packet delta на okna? Какие `op`?
3. Для `document_реализациятмц`: фактические `tmp3_key.key_cols`, доля `row_key` вида
   GUID / `guid#…` / `sha1`, sample стыковки `key_text`↔`row_key`.
4. Пишет ли apply rows при пустом `base_profile.key_props` на крупных сущностях?
5. Нужен ли restore `tmp_changed_rows_keep`, если sync rows не трогает (кто ещё может
   wipe)?

### По докам SereneDB / сборке 26.07.3 (обязательно `search_docs`+`read_section`+живой probe)

6. **`MERGE … WHEN MATCHED THEN DELETE`** и **`WHEN NOT MATCHED BY SOURCE THEN DELETE`**
   — поведение на 26.07.3 с большим target и узким source (доки:
   `sql/statements/merge_into`; cookbook SCD). Можно ли безопасно ограничить NOT MATCHED
   BY SOURCE предикатом по списку кандидатов?
7. Атомарность chunked-MERGE / mid-abort — уже заложено в FIX_PLAN этап 6 как
   «недоступна на 26.07.3»; подтвердить, что partial DELETE+xfer не добавляет нового
   класса дыр.
8. Upsert-батчи / `hash(row_key)%n_parts` — достаточно ли существующих `tmp3_merge_jobs`
   для partial, или нужен иной chunking.
9. Temp tables + `query_table(entity)` с полу-джойном на миллионы строк — лимиты памяти
   vs текущий cell-budget чанков.
10. Есть ли штатный **primary key / INDEX** на `search_corpus(src_table,row_key)` для
    ускорения anti-join partial (или достаточно текущего физического порядка)?

### По продуктовому контракту полной B

11. Для fold/sha1: выбираем (A) side-table vkey, (D) fallback entity-rebuild на gone, или
    иной путь владельца — без смены `row_key`.
12. Считать ли «row-level» для документов официально **object-level (Ref_Key)**, и
    фиксировать это в спеке B (ожидания wall-time).
13. HTTP-only инсталляции: блокировать `partial_rebuild=1` без rows (fail-closed) или
    писать rows из HTTP-синка?
14. Критерий приёмки B: wall p_doc realiz при 1 delta-doc; md5/emb baseline сущности;
    vector_loss_gate; такты №1/№2 как в v10.
15. Порядок относительно FIX_PLAN этапа 6: полная B **после** xfer-before-DELETE или
    допускается только вместе с ним?

---

## Источники (якоря)

- `.claude/state/plan-takt-fix-v10.md` — A/B0/C/D, waiver полной B
- `ubuntu/serenedb/pipeline.sh:43-66`
- `ubuntu/serenedb/corpus_build.sql:997-1013, 1336-1347, 1382-1534, 2169-2227`
- `ubuntu/serenedb/corpus_merge.sql:4-6, 506-561, 855, 887-915, 1003-1004`
- `ubuntu/packet/packet_apply.py:578-714, 717-750, 886-940, 998-1034`
- `ubuntu/serenedb/changed_sources_sql.py:1-32`
- `docs/audit/FIX_PLAN_2026-09-02.md` этап 6
- SereneDB docs: `https://docs.serenedb.com/sql/statements/merge_into`
