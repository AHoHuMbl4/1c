# С2 — подмена словаря синонимов на okna (27.08.2026)

База: **okna** (`gpu-erw:2202`, SereneDB `127.0.0.1:7890`).  
Источник новой редакции: боковая таблица `alias_okna_c1` (С1).  
Боевая: `search_entity_alias`. `serene_ask.py` не трогали.

Доки (штатные средства): [CREATE TABLE … AS SELECT (CTAS)](https://docs.serenedb.com/sql/statements/create_table#create-table--as-select-ctas),
[MERGE INTO](https://docs.serenedb.com/sql/statements/merge_into),
[INSERT … SELECT](https://docs.serenedb.com/sql/statements/insert),
[solr_synonyms](https://docs.serenedb.com/sql/statements/create_text_search_dictionary/solr-synonyms),
[Querying an inverted index](https://docs.serenedb.com/sql/indexes/inverted#querying-an-inverted-index)
(+ `VACUUM (REFRESH_TABLE)`).

---

## 1. Мера до / после (`alias_rank_bench` формула)

Прибор: ранжирование `tfidf` по индексу алиасов (`aliases @@ вопрос`), эталон —
`src_table` из gold okna (23 вопроса). Модель не зовётся.

| Словарь | индекс | эталон лидер | в тройке | не найден | из |
|---|---|---:|---:|---:|---:|
| **ДО** `search_entity_alias` (после починки пустого индекса) | `alias_idx` | **0** | **0** | **22** | 23 |
| **ДО** боковая `alias_okna_c1` | `alias_okna_c1_idx` | **0** | **1** | **21** | 23 |
| **ПОСЛЕ** подмены (= c1) | `alias_idx` | **0** | **1** | **21** | 23 |

Числа «до» на проде и «после» совпадают с боковой: подмена перенесла c1
как есть. Полные вопросы почти не дают лидера: `search_dict` без стемминга,
склонения («клиентов») ≠ токены алиасов («клиенты»).

### Токен-пробы (честный сигнал обиходных слов)

| терм | ДО (prod) | ПОСЛЕ / c1 |
|---|---|---|
| `клиент` | — | — |
| `клиенты` | — | **`catalog_контрагенты`** |
| `клиентов` | — | — |
| `контрагент` | `catalog_контрагенты` | — (в новой строке нет singular) |
| `продажа` | — | `document_реализациятмц` (+экспорт/услуги) |
| `номенклатура` | `catalog_номенклатура` | `catalog_номенклатура` |

### Находка: `alias_idx` был пуст

До любой подмены: `SELECT count(*) FROM alias_idx` → **0** при 254 строках
таблицы. После `DROP`+`CREATE` (+ `VACUUM (REFRESH_TABLE)`) → 254, затем после
MERGE → 257. Без пересборки индекс молча не участвовал в ранжировании.

---

## 2. Сверка составов

| | prod (до) | `alias_okna_c1` | prod (после) |
|---|---:|---:|---:|
| строк | 254 | 258 (257 distinct) | **257** |
| непустых aliases | 254 | 258 | 257 |
| avg `length(aliases)` | **55** | **84** | **84** |

- Только в новой (нет в старой):  
  `chartofcharacteristictypes_характеристикинедвижимогоимущества`,  
  `document_установкаценноменклатуры_номенклатуры`,  
  `informationregister_характеристикинедвижимогоимущества`.
- Только в старой: **нет**.
- Дубль в c1: `informationregister_контактнаяинформация` ×2 → после MERGE
  одна строка (257 = 254 − 0 + 3).

### Где заметно богаче (Δlen топ)

`catalog_значенияданныхсотрудников` (+99), `documentjournal_кадры` (+87),
`documentjournal_тмцнаответственномхранении` (+86), …
`catalog_контрагенты`: было «Контрагенты, контрагент, дни отсрочки…» →
стало **«Контрагенты, клиенты, поставщики, список партнеров»**.

### Где новая ХУЖЕ старой (риск)

По длине (Δ ≤ −10), примеры:

| src_table | old | new | что потеряно (снимок) |
|---|---:|---:|---|
| `calculationregister_данныенксс` | 138 | 70 | больничные, взносы работодателя… |
| `document_расчетотпускных` | 96 | 35 | вид отпуска, вид удержания… |
| `document_инвентаризационнаяопись_номенклатура` | 158 | 100 | количество/сумма в алиасах |
| `catalog_классификатортарифовэаизл` | 106 | 68 | код категории, размер… |
| `document_авансовыйотчет` | 47 | 32 | «приложено док» |
| … | | | ещё ~10 с Δ от −9 до −26 |

Отдельно: singular **`контрагент`** ушёл из алиасов `catalog_контрагенты`
(осталось «клиенты») — токен-проба `контрагент` после подмены пуста.

---

## 3. Бэкап

```sql
CREATE TABLE search_entity_alias_bak_20260827 AS
  SELECT * FROM search_entity_alias;
-- [замер] 254 строки
```

---

## 4. Подмена (одним запросом)

```sql
MERGE INTO search_entity_alias AS t
USING alias_okna_c1 AS s
ON (t.src_table = s.src_table)
WHEN MATCHED THEN UPDATE SET
  aliases = s.aliases,
  best_used_for = s.best_used_for,
  not_enough_for = s.not_enough_for,
  seen_at = s.seen_at
WHEN NOT MATCHED BY TARGET THEN INSERT
  (src_table, aliases, best_used_for, not_enough_for, seen_at)
  VALUES (s.src_table, s.aliases, s.best_used_for, s.not_enough_for, s.seen_at)
WHEN NOT MATCHED BY SOURCE THEN DELETE;
-- MERGE 258; итог 257 distinct
```

Затем: `DROP INDEX alias_idx` + `CREATE INDEX … USING inverted(aliases search_dict, src_table) INCLUDE (src_table)` +
`VACUUM (REFRESH_TABLE) search_entity_alias` + `GRANT SELECT … TO serene_ro`.

---

## 5. Пересборка `search_dict_syn`

Компилятор: логика `ubuntu/serenedb/solr_synonyms_build.py` (`compile` ←
`search_entity_alias` → DROP+CREATE `solr_synonyms`).  
Результат: **257 правил / 40 361 байт** (раньше ~221 / ~23 КБ).

### Мишень-блокер

```text
SELECT ts_lexize('search_dict_syn','клиент');
-- ДО:  {клиент}
-- ПОСЛЕ: {клиент}    ← связь с каталогом НЕ появилась
```

```text
SELECT ts_lexize('search_dict_syn','клиенты');
-- ПОСЛЕ: {Контрагенты,клиенты,поставщики,"список партнеров"}
```

**Разбор (не подгонка):** в правиле Solr лежит слово **«клиенты»**, не
**«клиент»**. Словарь `solr_synonyms` не стеммит: singular query не входит в
класс. Генератор С1 дал plural everyday-word — мишень из PLAN/блокера
сформулирована на singular. Чинить данные своим скриптом нельзя (п. 20);
править генератор/повтор С1 — отдельный шаг.

`ASK_SOLR_SYNONYMS` на боевом `:8091` **выключен** (пустой env).

---

## 6. Контрольные вопросы (живой `/ask` + `ab_scorer`)

SQL-истина корпуса в тот же момент: **141** и **1891**.

| вопрос | эталон | kind | итог |
|---|---:|---|---|
| сколько клиентов реально покупают? | 141 | clarify | **FAIL** (в тексте фигуры вроде 353 / 4472) |
| сколько позиций совсем не продаётся в этом месяце? | 1891 | clarify | **FAIL** (got 1,4472) |

Прогон: `AB_CONTOUR=okna AB_GOLD_FILE=/tmp/c2-k6.tsv` → `ab_scorer.py` на
`http://127.0.0.1:8091/ask`, верных **0/2**, ~20 с. Подмена словаря одна
не закрыла K6 на текущем боевом контуре (флаг Solr выкл.; singular
`клиент` в dict не связан).

---

## 7. Откат

```sql
-- вернуть таблицу из бэкапа (штатный MERGE / или DELETE+INSERT)
DELETE FROM search_entity_alias;
INSERT INTO search_entity_alias SELECT * FROM search_entity_alias_bak_20260827;
DROP INDEX IF EXISTS alias_idx;
CREATE INDEX alias_idx ON search_entity_alias
  USING inverted(aliases search_dict, src_table) INCLUDE (src_table);
GRANT SELECT ON alias_idx TO serene_ro;
VACUUM (REFRESH_TABLE) search_entity_alias;
-- затем: python3 solr_synonyms_build.py compile --dsn "$DSN" --apply
```

Боковую `alias_okna_c1` и бэкап не дропать, пока С2/скор не закрыты.

---

## Вывод

1. Новый словарь **богаче по объёму** (avg 55→84) и впервые кладёт
   **«клиенты»** на `catalog_контрагенты`; токен `продажа` начинает бить в
   реализацию.
2. Мера `alias_rank_bench` на okna-gold: **0/0/22 → 0/1/21** (слабый плюс,
   на уровне одной тройки).
3. Записанный блокер `ts_lexize(…,'клиент')` → связь с каталогом **не снят**.
4. Оба K6 на живом ask **не сошлись** (clarify).
5. Риск: у части сущностей алиасы стали короче (меры/реквизиты выпали);
   singular `контрагент` пропал из строки контрагентов.
6. Побочная починка: пересобран пустой `alias_idx`.
