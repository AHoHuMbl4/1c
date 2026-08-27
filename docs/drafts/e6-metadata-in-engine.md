# Э6: чтение `$metadata` тактом — силами движка (долг п. 20)

Черновик решения. Код пайплайна **не** менялся. Живые серверы **не** трогались.
Оркестратор может применить вариант по этому файлу без повторного поиска.

Связанные якоря контракта/аудита:

- `docs/PLAN_TO_TARGET.md` — **Э6** (долг такта, решение владельца 26.08).
- `docs/TICK_PSQL_AUDIT.md` — заход **2-тер packet_config**: **(а) + долг** (разбор локального файла вне движка; ярлык «поход в 1С» снят как неверный).
- `TARGET.md` п. 20 — данные внутри SereneDB; разрешённый остаток «поход в 1С по OData» **не** покрывает чтение локального снимка.

---

## 1. Где сейчас читается `$metadata`

### 1.1. Целевой долг Э6: шаг такта `packet_config` (процесс клиента)

| Что | Где |
|---|---|
| Вызов из такта | `ubuntu/serenedb/build.sh:321-336` — при `PACKET_BASE_ID` шаг `== 2-тер. пересчёт контура агента`, `python3 …/packet_config.py "$PACKET_BASE_ID"` |
| Процесс | клиент Python (`packet_config.py`), **не** процесс `serened` |
| Файл на диске | `<PACKET_META_DIR>/<base_id>/$metadata`, default `PACKET_META_DIR=/var/lib/serenedb/packet-meta` (`ubuntu/packet/packet_config.py:52-55`, `ubuntu/packet/packet_apply.py:588-593`) |
| Кто кладёт файл | `packet_apply._apply_metadata` — чанк `metadata` из пакета → атомарно файл (`ubuntu/packet/packet_apply.py:596-615`, вызов `804-806`) |
| Выход шага | **не** таблица движка: JSON `/etc/1c-packet-bases.json` (поле `config.entities` + `config_version`) и строки `search_entity_skipped` (`packet_config.py:259-270`, `387-403`) |

Чтение и разбор XML **вне движка**:

1. **only_binary / props** — `ubuntu/packet/packet_config.py:285-290` (`open` + `f.read()`), разбор `133-139` (`_props_by_type`, regex `EntityType` / `Property`), применение `252-253` (`_only_binary` в `compute_contour`).
2. **Бутстреп EntitySet** (пустая `base_profile`) — `ubuntu/packet/packet_config.py:356-367` (второй `open` того же файла), разбор `142-146` (`_entity_sets`).

Контур по витрине уже **внутри** движка одним SQL (`_contour_sql`, `207-232`); долг — только кусок «снимок XML → props / EntitySet».

Оффлайн-замер формата на стенде (чтение файла, без правок сервера): `ut` — ~4,2 МБ текста UTF-8, **2835** `EntityType` и **2835** `EntitySet`. В комментарии `build.sh:161` для HTTP-шлюза зафиксировано **16 652 877** байт `read_text('$GATE/$metadata')`. Лимит `read_text` в доках — **3,9 GiB** (см. §2) — наш размер покрыт с запасом.

### 1.2. Уже штатно в движке (не долг Э6, образец закрытия)

Сборка корпуса **уже** читает тот же снимок силами движка:

```31:35:ubuntu/serenedb/corpus_build.sql
-- ============ 1. $metadata: движок сам ходит в 1С и сам разбирает XML ============
CREATE OR REPLACE TABLE tmp3_ent AS
SELECT lower(regexp_extract(b,'Name="([^"]+)"',1)) AS entity, b AS body
FROM (SELECT unnest(regexp_extract_all(content,'(?s)<EntityType\s.*?</EntityType>')) AS b
      FROM read_text(:'gate' || '/$metadata'));
```

- Запуск: `ubuntu/serenedb/build.sh:255-256` (`psql … -v gate="$GATE" -f corpus_build.sql`).
- `GATE="${ETL_ODATA_BASE:-…}"` (`build.sh:32`): в packet-режиме это **каталог** `<PACKET_META_DIR>/<base_id>`, не URL — тот же файл, что читает `packet_config` (`packet_apply.py:588-591`).
- Дальше: `tmp3_prop` / `tmp3_key` теми же `regexp_extract` / `regexp_extract_all` (`corpus_build.sql:37-67`).

То есть для корпуса п. 20 по `$metadata` уже исполнен; Э6 — дотянуть **тот же приём** до шага 2-тер.

### 1.3. Соседние чтения (вне периметра применения Э6, но той же природы на packet)

| Место | Режим | Как читает | Файл:строка |
|---|---|---|---|
| `poc_load_entity._read_meta_xml` / `_load_metadata` | packet: `open` файла; HTTP: `urlopen …/$metadata` | `95-130` | ключи/типы в кэш процесса |
| `odata_census.metadata` / `entity_sets` | packet → `L._read_meta_xml`; HTTP → сеть | `105-132` | перепись |
| `serene_sync._service_skip` → `L.only_binary` | тянет `_load_metadata` | `215-216`, `poc_load_entity.py:514-547` | skip «двоичное» |
| `serene_search_build` | HTTP `$metadata` | `113-122` | **выведен** из боевого такта (см. Э5); не трогать в Э6 |

На **HTTP**-контуре чтение `$metadata` по OData — разрешённый остаток п. 20. На **packet** те же функции читают **локальный файл** — та же дыра, что у `packet_config`, но Э6 по плану закрывает **шаг такта 2-тер**. Расширение на sync/load — отдельным заходом после того же SQL-образца.

---

## 2. Штатные средства движка (доки SereneDB)

Отрицательные выводы ниже — только после `search_docs` + `read_section`.

### 2.1. Что подходит под наш формат (большой XML `$metadata` 1С)

| Средство | Url раздела | Покрытие нашего случая |
|---|---|---|
| **`read_text`** | https://docs.serenedb.com/cookbook/file_formats/read_file#read_text | Читает файл (или HTTP URL при httpfs) в одну строку `content` VARCHAR; лимит **3,9 GiB**; UTF-8. **Это канон уже в бою** (`corpus_build.sql:35`). Локальный путь packet-meta — тот же table function. |
| **`read_blob`** | https://docs.serenedb.com/cookbook/file_formats/read_file#read_blob | Запас, если UTF-8 сломан; для штатного `$metadata` 1С не нужен. |
| **`regexp_extract` / `regexp_extract_all`** | https://docs.serenedb.com/sql/functions/regular_expressions#using-regexp_extract | Разбор XML **без** XML-типа: те же паттерны, что Python (`EntityType`, `Property`, `EntitySet`, `Key`). Уже доказано на полном снимке в `corpus_build.sql`. RE2; флаг `(?s)` для multiline — как в боевом SQL. |
| Remote HTTP + SECRET | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#querying-remote-files ; секреты: https://docs.serenedb.com/configuration/secrets_manager#types-of-secrets | Для **варианта (б)** и для HTTP-корпуса: `read_text('http://…/$metadata')` с `TYPE http` SECRET (как `build.sh:163`). На packet-контуре шлюз 1С на Ubuntu **может отсутствовать** — файл уже привезён агентом. |

### 2.2. Что **не** покрывает формат `$metadata`

| Средство | Url | Почему не закрывает Э6 само по себе |
|---|---|---|
| **`read_json` / COPY FORMAT json** | https://docs.serenedb.com/data_import_and_export/json/loading_json#the-read_json-function ; https://docs.serenedb.com/sql/statements/copy#overview | Штатная «загрузка JSON». Снимок 1С — **OData CSDL XML**, не JSON. `read_json` к `$metadata` неприменим без предварительной конвертации (своей обработки — запрет п. 20). |
| **XML type / xml*** | https://docs.serenedb.com/compatibility#xml-types ; фрагмент таблицы: https://docs.serenedb.com/compatibility/core-sql-compatibility#xml | «PostgreSQL's XML data type and related functions are **not planned**.» Нативного XML-парсера нет — только текст + regexp (как сейчас в корпусе). |
| **COPY FROM** CSV/Parquet/JSON | https://docs.serenedb.com/sql/statements/copy#overview | Форматы импорта — CSV, Parquet, JSON; сырой CSDL XML в перечень COPY не входит. |

**Итог по докам:** штатное чтение файла — `read_text`; штатный разбор структуры `$metadata` в нашей сборке — `regexp_*` по VARCHAR. «Штатная загрузка JSON» из формулировки Э6 к **этому** артефакту не подходит; эквивалент по смыслу п. 20 — уже принятый в проекте путь `read_text` + regexp (доказан `corpus_build`).

---

## 3. Два варианта решения

### (а) Движок читает сам (рекомендуемый)

**Суть:** убрать `open`/`re` по `$metadata` из `packet_config.py`; props, `only_binary` и бутстреп-EntitySet считать **одним (или двумя) SQL** через `read_text` того же файла, по образцу `corpus_build.sql:32-41`.

**Точный запрос (черновик для внедрения — не применять в этой задаче):**

Путь снимка в переменной psql, например `-v meta_path=/var/lib/serenedb/packet-meta/<base_id>/$metadata` (или склейка каталога как у `gate`).

```sql
-- 1) свойства EntityType (аналог _props_by_type; регистр имени как в EntityType/@Name)
CREATE OR REPLACE TEMP TABLE pkt_meta_prop AS
SELECT
  regexp_extract(b, 'Name="([^"]+)"', 1) AS entity,
  x.prop AS prop,
  x.edm AS edm
FROM (
  SELECT b,
         regexp_extract(s, '<Property\s+Name="([^"]+)"\s+Type="([^"]+)"',
                        ['prop', 'edm']) AS x
  FROM (
    SELECT unnest(regexp_extract_all(content, '(?s)<EntityType\s.*?</EntityType>')) AS b
    FROM read_text(:'meta_path')
  ) e,
  LATERAL (
    SELECT unnest(regexp_extract_all(b, '<Property\s+Name="([^"]+)"\s+Type="([^"]+)"')) AS s
  ) p
);

-- 2) only_binary: семантика poc_load_entity.only_binary / packet_config._only_binary
--    (blob ∧ ¬human; lookup entity OR entity||'_RecordType')
CREATE OR REPLACE TEMP TABLE pkt_only_binary AS
WITH base AS (
  SELECT entity, list(prop) AS names, list(edm) AS edms,
         list(struct_pack(prop := prop, edm := edm)) AS pairs
  FROM pkt_meta_prop
  GROUP BY entity
),
resolved AS (
  -- для каждой кандидатной сущности контура: взять props сущности или *_RecordType
  SELECT c.entity AS contour_entity,
         coalesce(b1.pairs, b2.pairs) AS pairs,
         coalesce(b1.names, b2.names) AS names,
         coalesce(b1.edms, b2.edms) AS edms
  FROM (SELECT DISTINCT entity FROM /* подставить список контура или base_profile */) c
  LEFT JOIN base b1 ON b1.entity = c.entity
  LEFT JOIN base b2 ON b2.entity = c.entity || '_RecordType'
),
flags AS (
  SELECT contour_entity,
         len(coalesce(pairs, [])) > 0 AS known,
         (list_contains(names, list_filter(names, n -> n LIKE '%_Base64Data')[1]) -- упростить:
          OR list_filter(edms, t -> t IN ('Edm.Stream', 'Edm.Binary')) != []) AS blob
         -- human: Edm.String без суффиксов _Type/_Key/_Base64Data, не в typed,
         -- не Ref_Key/DataVersion/Predefined/PredefinedDataName
  FROM resolved
  -- … довести до байт-в-байт с Python в замке (см. §6)
  WHERE false  -- заглушка: в коммите внедрения заменить полным CASE
);
```

Практичнее на внедрении (меньше риска расхождения list-семантики):

1. SQL отдаёт таблицу `(entity, prop, edm)` через `psql -tA --csv` (как уже `_rows` в `packet_config.py:112-120`).
2. `_only_binary` **оставить в Python на словаре props**, но словарь строить **не** из `open`, а из результата SQL — это **ещё не** полное (а).  
   **Полное (а):** вердикт `only_binary` тоже в SQL (один SELECT списка `entity`, где признак истинен) + бутстреп:

```sql
SELECT DISTINCT regexp_extract(unnest(
         regexp_extract_all(content, '<EntitySet\s+Name="([^"]+)"')),  -- уточнить форму unnest
       …)
FROM read_text(:'meta_path');
-- Проще и уже в стиле корпуса:
SELECT unnest(regexp_extract_all(content, '<EntitySet\s+Name="([^"]+)"', 1)) AS entity_set
FROM read_text(:'meta_path');
```

(Проверить на живой сборке 26.08.x форму `regexp_extract_all(..., group)` — в корпусе group=1 уже используется для `PropertyRef`: `corpus_build.sql:52-53`.)

**Что меняется в `build.sh`:** минимально — **ничего**, если SQL зовётся изнутри `packet_config.py` через существующий `_rows(dsn, sql)` с подстановкой пути. Альтернатива: отдельный `psql -f` с новым SQL-файлом (завести при внедрении; в дереве сейчас нет) и `-v meta_path=…` перед/вместо куска Python — тогда в `build.sh:321-336` одна строка `psql` + упрощённый Python только для записи JSON баз (запись `/etc/1c-packet-bases.json` — конфиг агента, не разбор данных корпуса; её вынос в SQL не требуется для закрытия Э6).

**Что уходит из Python:** `open(snap)` в `_read_sources` (`285-290`) и в бутстрепе (`356-361`); при полном (а) — также `_props_by_type` / `_entity_sets` как читатели файла (логика `_only_binary` переезжает в SQL или остаётся чистой функцией над уже готовым результатом движка без I/O данных).

**Зависимость от порядка такта:** не опираться на `tmp3_prop` корпуса — при `SKIP_BUILD=1` сборка не перечитывает `$metadata`, а `packet_config` всё равно должен видеть **текущий** файл после apply. Свой `read_text(:'meta_path')` в шаге 2-тер обязателен.

### (б) Честный вынос в поход OData

**Суть:** объявить чтение метаданных для контура агента **походом в 1С по OData** (разрешённый остаток п. 20): `GET {ODATA}/$metadata` с токеном шлюза, разбор ответа процессом, который уже имеет право на OData (как HTTP-ветка `poc_load_entity._load_metadata`, `121-125`).

**Как выглядит шаг:**

1. Из такта **убрать** зависимость шага 2-тер от локального `<PACKET_META_DIR>/…/$metadata` для props/EntitySet.
2. Задать на packet-юните URL шлюза 1С + `ODG_GATEWAY_TOKEN` (сейчас packet часто живёт **без** живого OData на Ubuntu — данные только из пакетов).
3. `packet_config` (или тонкий вызов `odata_census.metadata()` / HTTP-ветка) качает XML по сети каждый пересчёт контура.
4. Файл снимка от `packet_apply` остаётся для **`corpus_build`** (`read_text` локального пути) — либо корпус тоже переводят на URL (дубль канала).

**Что уходит из такта как «долг файла»:** локальный `open` в `packet_config`.  
**Что появляется:** сетевой OData-клиент в шаге, который сегодня работает офлайн относительно 1С; второй источник правды (файл apply vs live metadata) и рассинхрон, если агент ещё не выгрузил новую конфигурацию, а шлюз уже отдал другую.

**Почему это «честно» по п. 20:** ярлык совпадает с перечнем («поход в 1С … по OData»).  
**Почему плохо для packet-продукта:** ломает модель «Ubuntu без 1С, метаданные едут пакетом» (`packet_apply.py:588-592`, решение владельца 06.08 про боевые скрипты сборки).

---

## 4. Рекомендация

**Вариант (а)** — движок `read_text` + `regexp_*`, как в `corpus_build.sql`.

Обоснование:

1. Доки дают `read_text` и regexp; XML-типа нет — и корпус уже закрыл этот пробел тем же приёмом (url §2.1).
2. Артефакт уже на диске от apply; повторный OData не нужен и на части установок невозможен.
3. ТICK_PSQL_AUDIT прямо указывает закрытие: «**(а)** через штатный `read_text` того же снимка (как уже делает `corpus_build`)».
4. Вариант (б) маскирует долг ярлыком п. 20, но ухудшает автономность packet и плодит два канала метаданных.

Промежуточного «оставить `open`» нет (решение владельца 26.08).

---

## 5. Список правок по файлам (точный, **не применять** в Э6-исследовании)

| Файл | Правка |
|---|---|
| `ubuntu/packet/packet_config.py` | Удалить `open(snap)` в `_read_sources` (285-290) и бутстрепе (356-361). Добавить SQL-константы / загрузку props и EntitySet через `_rows` + `read_text`. При полном (а) — SQL-список `only_binary` сущностей; `compute_contour` принимает set/таблицу вердиктов без разбора XML. Обновить модульный docstring (15-16, 52-54, 187-189). |
| `ubuntu/packet/test_packet_config.py` (и связанные оффлайн-пробы) | Фикстура: вместо подмены `open` — подмена `_rows` с ответом «как от SQL» **или** временный файл + живой `read_text` на dev-DSN (если проба с движком). Замок: число keep/skip / WHY_BINARY совпадает с прежним эталоном на том же XML. |
| `ubuntu/serenedb/build.sh` | Только если SQL выносится в отдельный `-f`: между 2-бис и записью конфига — `psql -v meta_path=… -f …`. Иначе **без изменений** (321-336 остаются `python3 packet_config`). |
| опционально: новый `.sql` рядом с `packet_config.py` (в дереве **ещё нет** — завести при внедрении) | DDL TEMP + SELECT only_binary / EntitySet; в шапке коммита внедрения: `Доки: cookbook/file_formats/read_file#read_text`. |
| `docs/TICK_PSQL_AUDIT.md` | Заход 2-тер: снять «долг», оставить **(а)** после замера. |
| `docs/PLAN_TO_TARGET.md` | Э6 — закрыт ссылкой на замер/коммит. |
| `docs/TARGET_STATUS.md` / `memory_bank/activeContext.md` / `CHANGELOG.md` | Статус долга п. 20 / Э6. |
| `memory_bank/mcp-memory.json` | Наблюдение на сущность `packet_config` / такт: `$metadata` только через `read_text`. |
| **Не трогать в Э6** | `corpus_build.sql` (уже эталон); `packet_apply._apply_metadata` (доставка файла остаётся); HTTP-OData в `poc_load_entity` (отдельный контур). |

---

## 6. Как доказать правку замером

**Оффлайн (обязательный замок до выката):**

1. Прогон `python3 ubuntu/packet/test_packet_config.py` (и расширенный кейс с XML-фикстурой, где есть хотя бы одна only_binary сущность — семантика как `poc_load_entity.only_binary`, замер 05.08: узкий класс двоичных).
2. На одном и том же файле `$metadata`:  
   - **до:** `props`/`EntitySet` из Python `open`+regex;  
   - **после:** те же множества из SQL `read_text`+regexp.  
   Критерий: `set(EntitySet)` равен; множество `entity`, для которых `_only_binary` / SQL-флаг истинен, равно (байт-в-байт список имён).
3. Регрессия контура: на фикстуре с непустой «переписью» число `keep` / причины `WHY_BINARY` / `WHY_SHADOW` совпадают с записью до правки (в тестах уже есть якоря `/* contour */`).

**Живой (packet-база, без смены данных 1С):**

1. Сохранить копию текущего `/etc/1c-packet-bases.json` → `config.entities` и `SELECT entity, why FROM search_entity_skipped ORDER BY 1`.
2. Выкатить правку; `PACKET_BASE_ID=<id> python3 packet_config.py <id>` (или один такт `build.sh` с тем же id).
3. **После:** `config_version` не обязан расти, если список entities бит-в-бит тот же; при росте — diff entities пуст по смыслу (только порядок/версия). `search_entity_skipped` с `why` = `WHY_BINARY` — тот же набор.
4. Дополнительно (движок):  
   `psql "$DSN" -tAc "SELECT count(*) FROM read_text('/var/lib/serenedb/packet-meta/<id>/$metadata')"` → `1`;  
   `SELECT count(*) FROM (SELECT unnest(regexp_extract_all(content,'(?s)<EntityType\s.*?</EntityType>')) FROM read_text('…')) t` → равно числу EntityType снимка (для `ut` в пробе чтения — **2835**).

**Не считать доказательством:** «SQL выполнился без ошибки» без сравнения списков entities/skip с до-снимком.

---

## 7. Краткие ответы оркестратору

| Вопрос | Ответ |
|---|---|
| Какой процесс долга? | `python3 packet_config.py` из `build.sh` шага 2-тер |
| Какой файл? | `/var/lib/serenedb/packet-meta/<base_id>/$metadata` |
| Какой выход сегодня? | JSON баз агента + `search_entity_skipped`, не таблица props |
| Есть ли штатный XML? | Нет (compatibility XML not planned) |
| Есть ли штатное чтение файла? | Да: `read_text` |
| Образец в дереве? | `corpus_build.sql:32-41` |
| Рекомендация? | **(а)** перенести разбор в SQL; **(б)** только если владелец сознательно возвращает OData на packet-такт |

Конец черновика Э6.

---

## 8. Реализовано (27.08)

**Вариант (а)** в `ubuntu/packet/packet_config.py` (без правок `build.sh`).

| Что | Как |
|---|---|
| Убрано | `open(snap)` в `_read_sources` и второй `open` в бутстрепе `run` |
| Добавлено | `_metadata_sql(path)` → один SELECT с якорем `/* metadata */`: `read_text(path)` + `regexp_extract_all` EntityType/Property/EntitySet (форма как `corpus_build.sql:32-41`); `_load_metadata` / `_meta_from_rows` собирают `props` и список EntitySet |
| Канал | тот же `_rows(dsn, sql)` / `psql -tA --csv` / `SERENEDB_DSN` — без новых env |
| Python | `_only_binary` / `compute_contour` / запись `/etc/1c-packet-bases.json` — без смены контракта; бутстреп берёт EntitySet из того же ответа metadata |
| Почему не `parse_json`/`read_json` | снимок — OData CSDL XML; штатная загрузка JSON к нему неприменима (§2.2). Эквивалент п. 20 — `read_text` + regexp |

**Доказано оффлайн:**

- `ubuntu/packet/test_packet_metadata_readtext.py` — **11/0** (нет `open(…$metadata…)`; есть `read_text`; регрессия `open(snap)` ловится; мок `_rows` даёт props/sets бит-в-бит с прежним regex).
- `ubuntu/packet/test_packet_config.py` — **50/0** (FakeDB эмулирует `/* metadata */`; бутстреп/only_binary/тени).
- Прочие `ubuntu/packet/test_*.py` — все `rc=0` (числа в CHANGELOG).

Живой замер entities/skip на packet-базе (§6) — за оркестратором/выкатом; код и оффлайн-замки закрывают долг чтения вне движка.
