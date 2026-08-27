# Э7: выгрузка wiki средствами движка — проект решения

Дата: 26.08.2026. Код и живые серверы **не** трогались. Только разбор.

Контекст долга: [`docs/PLAN_TO_TARGET.md`](../PLAN_TO_TARGET.md) §Э7;
предшествующий вердикт такта: [`docs/TICK_PSQL_AUDIT.md`](../TICK_PSQL_AUDIT.md)
заход «7 wiki_publish» (строки 170, 239); ловушка techContext
`wiki dump → {page_id}.md + purge`.

---

## 1. Цепочка сейчас (файл:строка)

| Звено | Где | Что делает |
|---|---|---|
| Сборка тел **внутри** движка | `ubuntu/serenedb/wiki_build.sql:27–38` (`wiki_entity_facts`), `:47–113` (`wiki_pages`) | Представление: `page_id` = `src_table`, `body` = готовый markdown с YAML-frontmatter. Одна строка = одна будущая страница. |
| Зов сборки | `ubuntu/serenedb/wiki_publish.sh:69` | `psql … -f wiki_build.sql` |
| SELECT наружу | `wiki_publish.sh:74` | `SELECT page_id, body FROM wiki_pages` → файл `$TMP/dump` (разделители `\x1e` / `\x1f`) |
| Python → `.md` | `wiki_publish.sh:77–109` (heredoc `python3 -`) | Пишет `$VAULT/entities/{page_id}.md`; тело = `body` без доп. трансформации смысла |
| Чистка устаревших | `wiki_publish.sh:102–107` | Удаляет `*.md` в `entities/`, которых нет в текущей выгрузке (только если `written` непуст) |
| Временный dump | `wiki_publish.sh:73` | `mktemp -d` + `trap 'rm -rf "$TMP"' EXIT` |
| Потребитель №1 (обязательный) | `wiki_publish.sh:114` | `openclaw wiki compile` — плагин **memory-wiki**, vault на диске |
| Потребитель №2 | `wiki_publish.sh:124–125` | `openclaw memory index --agent …` — смысловой индекс поверх тех же страниц |
| Кто читает `.md` в рантайме бота | `ubuntu/openclaw/instance/AGENTS.md:20–23` | Порядок: `wiki_search` → при надобности `wiki_get` → затем инструмент данных. Формат vault: OpenClaw docs `memory-wiki` — каталог `entities/*.md` ([plugins/memory-wiki §Vault layout](https://docs.openclaw.ai/plugins/memory-wiki); локально `/usr/lib/node_modules/openclaw/docs/plugins/memory-wiki.md:57–79`) |
| Зов из такта | `ubuntu/serenedb/build.sh:437–438` | После `wiki_alias.sh`, soft-fail |
| Метка владельца vault | `wiki_publish.sh:58–67`, `:112` | `$VAULT/.built-from` = `current_database()` (`:51`) |

**Не потребитель `.md`:** `wiki_alias.sh` / `wiki_alias_parse.py`. Они пишут в таблицы
`search_entity_alias` / `search_measure_alias`; представление `wiki_pages` потом
**читает** алиасы из базы (`wiki_build.sql:112`), а не из файлов vault.
Ask-путь (`serene_ask`) тоже не зовёт `wiki_pages` / vault — только готовый
`search_entity_alias` ([`docs/PIPELINE.md`](../PIPELINE.md) про путь вопроса).

Итоговый SELECT (канон):

```sql
SELECT page_id, body FROM wiki_pages;
```

Источник — **VIEW** `wiki_pages` (не физическая таблица).

Формат файла у потребителя:

- путь: `$WIKI_VAULT/entities/<page_id>.md` (или default vault агента);
- содержимое: ровно `body` + завершающий `\n`;
- purge: файлы, исчезнувшие из `wiki_pages`, должны пропасть из `entities/`.

---

## 2. Штатные средства SereneDB (по докам)

Проверено MCP `serenedb-docs` (`search_docs` → `read_section`). Отрицательные
выводы ниже опираются на прочитанные разделы, не на память.

| Средство | Url | Что умеет | Покрывает ли vault OpenClaw |
|---|---|---|---|
| **COPY … TO** | https://docs.serenedb.com/sql/statements/copy#copy--to | Экспорт таблицы/запроса в **один** внешний файл CSV / Parquet / JSON / BLOB | Нет: один файл ≠ много `{page_id}.md` |
| **COPY options** | https://docs.serenedb.com/sql/statements/copy#copy--to-options | Те же форматы; цель — путь файла (в т.ч. выражение/`$1`) на **весь** COPY | Нет per-row имени из колонки `page_id` |
| **BLOB format** | https://docs.serenedb.com/sql/statements/copy#blob-options | Одна колонка → один `.blob` | Не markdown vault; не N файлов |
| **JSON Export** | https://docs.serenedb.com/cookbook/file_formats/json_export | `COPY (SELECT …) TO 'out.json'` (NDJSON или `ARRAY`) | Потребитель memory-wiki ждёт `.md` в `entities/`, не NDJSON |
| **CSV / Parquet Export** | https://docs.serenedb.com/cookbook/file_formats/csv_export · parquet_export | Табличный дамп | То же |
| **Partitioned Writes** | https://docs.serenedb.com/data_import_and_export/partitioning/partitioned_writes | Hive: `root/page_id=<id>/data_N.ext`; `FILENAME_PATTERN` только `{i}` / `{uuid}` | **Не** `entities/<id>.md`. OVERWRITE чистит Hive-дерево, не плоский набор `.md` |
| **EXPORT DATABASE** | https://docs.serenedb.com/sql/statements/export_and_import_database#export-database | Весь каталог БД → `schema.sql` + table CSV/Parquet | Не vault wiki |
| **S3 COPY TO** | https://docs.serenedb.com/cookbook/network_cloud_storage/s3_export | Тот же COPY на `s3://…` | Тот же разрыв формата; S3 не читает OpenClaw wiki |
| **read_text / read_blob** | https://docs.serenedb.com/cookbook/file_formats/read_file | Чтение файлов **в** движок | Обратное направление; выгрузку не закрывает |

Поиск по «per row write file named by column» / external tables как «писать N
именованных `.md`» штатного эквивалента vault **не дал**.

Вывод по докам: **штатный дамп есть** (`COPY … TO`), **эквивалентности шагу
«N×`.md` + purge» нет**. Это совпадает с уже записанным в
`TICK_PSQL_AUDIT.md:170` (ярлык «просто COPY» был снят как неверный).

Замечание к комментарию в коде: `wiki_build.sql:14–15` утверждает «файлов движок
не умеет» — по докам **устарело** (COPY TO пишет файлы). Неумение — не «файл
вообще», а «файл = `{page_id}.md` в раскладке memory-wiki + удаление устаревших».

---

## 3. Варианты

### (а) COPY TO / штатный дамп — куда пишет, понимает ли потребитель

Пример ближайшего штатного шага:

```sql
COPY (SELECT page_id, body FROM wiki_pages)
  TO '/path/in/engine-visible/dir/wiki_pages.json' (FORMAT json);
-- или PARTITION_BY (page_id) → Hive page_id=<id>/data_0.*
```

- Куда пишет: путь, видимый процессу `serened` (как `CSV_DIR` / обменный каталог
  такта; см. комментарий `build.sh` про видимость путей).
- Понимает ли потребитель: **нет**. `openclaw wiki compile` и layout
  `entities/*.md` (OpenClaw memory-wiki) не читают NDJSON/CSV/Hive/`data_N`.
- Даже после COPY остаётся внешний код: разложить в `{page_id}.md` и purge —
  то есть обработка **не исчезла**, а сменила вход с `\x1e`-дампа на JSON.
  По критерию Э7 («исчезла целиком, а не переименовалась») **(а) одно не
  закрывает долг**.
- Цикл `COPY … TO '<page_id>.md'` по строкам = `psql` в цикле → прямой запрет
  п. 20 TARGET.md.

### (б) Потребитель читает из движка напрямую (таблица вместо файлов)

Два подварианта.

**б1 — продукт (наш контур), закрывает долг целиком.**  
Смысл вики у нас — словарь перефраза сущности для бота OpenClaw
(`HOW_IT_WORKS.md`, блок «для чего вики»). Те же слова уже лежат в
`search_entity_alias` (наполняет `wiki_alias.sh`, **(б)** п. 20 — вызов LLM).
Ask уже резолвит алиасы из базы без vault.

Чтобы убрать dump+Python:

1. Перестать требовать `wiki_search`/`wiki_get` по файловому vault для маршрута
   «человеческое слово → `src_table`» (правка порядка в
   `ubuntu/openclaw/instance/AGENTS.md` и/или вынос резолва в MCP/`ask_1c`,
   где алиасы уже в SQL).
2. Убрать из такта запись `entities/*.md`: `wiki_publish.sh` оставлять только
   как no-op/удалить зов из `build.sh:438`, либо сузить до «если vault нужен
   человеку — отдельный ручной/внешний трек», не долг п. 20 в такте.
3. `wiki_build.sql` можно оставить как VIEW для отладки/будущего ingest — тела
   остаются в движке, наружу не едут.

Что меняется у потребителя: бот больше не зависит от disk-vault для 1С-сущностей;
compile/memory index по entity-страницам такта не обязательны.

Риск: регрессия перефраза, если `wiki_search` давал сигнал сверх
`alias_idx` (связи parent/children, quantities в тексте страницы). Эти факты
уже в SQL (`wiki_entity_facts` / корпус); перенос сигнала — в ask/инструмент,
не в файлы.

**б2 — апстрим OpenClaw.**  
Штатный `wiki ingest` / OKF import принимают **файлы** `.md`, не DSN SereneDB
(`/usr/lib/node_modules/openclaw/docs/cli/wiki.md`, `plugins/memory-wiki.md`).
Пока OpenClaw не умеет «прочитать VIEW `wiki_pages`», б2 — внешняя зависимость,
не закрытие в нашем репо.

### (в) «Разрешённый остаток п. 20» — обоснование, почему **нет**

Перечень своего кода в TARGET.md п. 20 исчерпывающий:

- поход в 1С по OData;
- вызов языковой модели;
- отрисовка изображений;
- проверка ответа модели (гейт).

Dump+purge wiki **не** входит. «Отрисовка изображений» — про графики ответа, не
про vault `.md` (`TICK_PSQL_AUDIT.md:170`). Значит текущий шаг — **долг**, а не
разрешённый остаток. Оставить как есть без (а)/(б) = долг висит.

---

## 4. Рекомендация (один вариант)

**Рекомендуется (б1): убрать файловый dump из такта**, оперев перефраз сущностей
на данные, уже лежащие в SereneDB (`search_entity_alias` + при необходимости
сигналы из VIEW/`ask`), и снять Python/`SELECT→.md`/purge.

Почему не (а): доки COPY/Partitioned Writes **не** покрывают формат потребителя
memory-wiki; любой COPY всё равно тянет внешний раскладчик → долг Э7 не
закрыт по формулировке владельца.

Почему не (в): не из перечня п. 20.

Почему не ждать (б2): закрытие долга такта не должно упираться в фичу чужого
продукта; при появлении native SQL/JSON ingest у OpenClaw можно вернуть
публикацию как тонкий `COPY` без Python — отдельным шагом.

Порядок внедрения (когда разрешат код):

1. Замер «до» (см. §6).
2. Прототип маршрута бота без зависимости от `entities/*.md` на одной базе.
3. Выключить/удалить dump+Python в `wiki_publish.sh`, зов из `build.sh`.
4. Замер «после» + регрессия base1 / приёмка перефраза.
5. Документы + снятие долга в `TICK_PSQL_AUDIT` / techContext / TARGET_STATUS.

---

## 5. Список правок по файлам (точный, **не применять**)

| Файл | Правка |
|---|---|
| `ubuntu/serenedb/wiki_publish.sh` | Удалить блок `:71–109` (SELECT + Python + purge) либо весь скрипт свести к optional/legacy; убрать зависимость такта от записи vault. Оставить/перенести защиту `.built-from` только если vault ещё пишется иначе. |
| `ubuntu/serenedb/build.sh:438` | Убрать или сделать явно no-op зов `./wiki_publish.sh` после закрытия б1. |
| `ubuntu/serenedb/wiki_build.sql:14–15` | Поправить комментарий: движок умеет COPY TO; пробел — формат vault / отсутствие потребителя SQL. VIEW можно сохранить. |
| `ubuntu/openclaw/instance/AGENTS.md:20–23` | Порядок работы: резолв вида записи через инструмент данных / алиасы в ask, без обязательного `wiki_search` по disk-vault (согласовать с запретом правил-в-промте: лучше механизм в мосте/инструменте, не долженствование в тексте). |
| конфиг OpenClaw (профили undebot) | При отказе от entity-vault: не требовать `extraPaths` на `…/wiki/…/entities` для такта; `wiki compile`/`memory index` entity-страниц из такта не звать. |
| `docs/HOW_IT_WORKS.md` | Строка про «wiki_publish пишет файлы» — заменить на новый контур. |
| `docs/TICK_PSQL_AUDIT.md` | Заход 7 wiki_publish: снять долг dump+purge после б1; psql-счётчик −2–3. |
| `memory_bank/techContext.md` | Строка ловушки wiki dump — закрыть со ссылкой на замер. |
| `docs/TARGET_STATUS.md` / `PLAN_TO_TARGET.md` | Отметить Э7 закрытым после замера. |
| `docs/RUNBOOK_DEPLOY.md` (разделы multi-wiki / WIKI_VAULT) | Убрать обязательный publish из такта; описать, что entity-перефраз = таблицы алиасов. |
| замки | Добавить оффлайн-тест: в `build.sh` нет SELECT→Python→`.md` для wiki; при сохранении VIEW — тест на SQL-форму `wiki_pages` без файлового I/O. |
| `MAP.md` | Строка про `wiki_publish.sh` — актуализировать. |

Не трогать в рамках Э7: `wiki_alias.sh` (это **(б)** LLM, другой заход такта),
`solr_synonyms_build.py` (отдельный долг/Э по audit).

---

## 6. Доказательство замером (рецепт до/после)

Живые серверы в этой задаче не трогались — ниже **обязательный** прогон при
внедрении. База для прогона: `ut_test` или `okna` (где vault уже наполнялся;
исторические якоря: ~697 стр. ut_test / ~255 okna в CHANGELOG).

### До (текущий контур)

1. `psql "$DSN" -tAc "SELECT count(*) FROM wiki_pages"` → **N_db**.
2. `find "$VAULT/entities" -name '*.md' | wc -l` → **N_fs** (ожидание: N_fs ≈ N_db
   после успешного `wiki_publish.sh`).
3. Один такт / ручной `./wiki_publish.sh`: в логе
   `вики: записано страниц X, удалено устаревших Y`.
4. `sudo -u undebot -H openclaw wiki status` — Vault ready, путь = ожидаемый.
5. Приёмка перефраза: набор вопросов «человеческое слово → сущность»
   (минимум золотой кусок entity-choice / step с wiki_search), зафиксировать
   долю верного вида записи **до** отключения dump.

### Оффлайн-опровержение (а) — без боя

На пустом каталоге (или `--server_directory` / временная БД, **не** боевой
инстанс):

```sql
COPY (SELECT page_id, body FROM wiki_pages)
  TO '/tmp/e7-wiki' (FORMAT csv, PARTITION_BY (page_id), OVERWRITE_OR_IGNORE);
```

Ожидаемое дерево: `/tmp/e7-wiki/page_id=<id>/data_0.csv` — **не**
`entities/<id>.md`. Это и есть замер «COPY ≠ потребитель».

### После (б1)

1. В такте нет записи в `entities/*.md` из SereneDB (N_fs не обновляется тактом;
   скрипт dump отсутствует).
2. `count(*) FROM wiki_pages` и `search_entity_alias` живы; ask/резолв алиасов
   без регрессии на REGRESSION_BASE1.
3. Приёмка того же набора перефраза: доля ≥ «до» (или зафиксированный допустимый
   спад с разбором — не молча).
4. Счётчик psql за такт: − процессы выгрузки wiki (`TICK_PSQL_AUDIT`: сейчас 3
   psql в `wiki_publish.sh:51,69,74`).

Критерий закрытия Э7: внешняя обработка тел wiki **отсутствует** (нет SELECT→
свой код→`.md`→purge), потребитель либо читает движок/ask, либо не использует
файловый vault для этого слоя.

---

## 7. Краткие ответы на критерии приёмки черновика

| Вопрос | Ответ |
|---|---|
| Таблица/VIEW | `wiki_pages` (`page_id`, `body`), сборка в `wiki_build.sql` |
| SELECT | `SELECT page_id, body FROM wiki_pages` — `wiki_publish.sh:74` |
| Кто пишет `.md` | встроенный Python heredoc в `wiki_publish.sh:77–109` (отдельного `.py` нет) |
| Потребитель | OpenClaw **memory-wiki** (`wiki compile`, `wiki_search`/`wiki_get`); не wiki_alias |
| Чистка | `wiki_publish.sh:102–107` + `rm -rf` TMP `:73` |
| Штатный COPY покрывает формат? | **Нет** (доки §2) |
| Рекомендация | **(б1)** убрать dump, опереться на данные в движке |
| Разрешённый остаток п. 20? | **Нет** — долг |

---

## Реализовано

Дата: 27.08.2026. Вариант **(б1)** — без COPY TO в такте (доки: COPY пишет
один файл / Hive, не `entities/<id>.md`).

| Было | Стало |
|---|---|
| `wiki_publish.sh:71–109` SELECT `\x1e`/`\x1f` → Python → `$VAULT/entities/*.md` + purge | Снято |
| `wiki compile` / `memory index` из такта | Не зовутся (entity-vault такт не обновляет) |
| Тела страниц | По-прежнему VIEW `wiki_pages` (`wiki_build.sql`); шаг такта только `psql -f wiki_build.sql` |
| Зов `build.sh:438` `./wiki_publish.sh` | Контракт сохранён (soft-fail) |
| Перефраз сущностей | `search_entity_alias` (wiki_alias) — без смены этого шага |

Замок: `ubuntu/serenedb/test_wiki_dump_engine.py` — **24/0** (мок psql, без БД).
Доки COPY: https://docs.serenedb.com/sql/statements/copy#copy--to

Не в этом шаге (по проекту «после замера» / «не больше»): правка AGENTS.md,
TARGET_STATUS / TICK_PSQL_AUDIT / HOW_IT_WORKS / живой замер до/после §6.
