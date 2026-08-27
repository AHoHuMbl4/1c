# С3 — морфология словаря синонимов на okna (27.08.2026)

База: **okna** (`gpu-erw:2202`, SereneDB **26.08.1** — живой `SELECT version()`;
в доках проекта часто фигурирует 26.07.3). `serene_ask.py` не трогали.

Проблема (С2): словарь знает слово только в записанной форме —
`ts_lexize('search_dict_syn','клиенты')` раскрывал класс, а `'клиент'` /
`'клиентов'` — нет. Мера `alias_rank_bench` на 23 q gold: эталон-лидер **0**.

---

## 1. Что нашёл в доках SereneDB

| Раздел | URL | Суть для задачи |
|---|---|---|
| Stemming and Stopwords | https://docs.serenedb.com/cookbook/search/stemming | `stemming=true` + locale → Snowball; индекс и запрос одним словарём |
| text template | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/text | стемминг, case, accent; нужен `frequency=true` для релевантности |
| stem template | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/stem | только стем; обычно внутри `pipeline` |
| pipeline | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/pipeline | цепочка: tokenizer → фильтр (в т.ч. solr_synonyms) |
| solr_synonyms | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/solr-synonyms | карта Solr inline; без стемминга сама |
| Synonyms cookbook | https://docs.serenedb.com/cookbook/search/synonyms | штатный путь: `pipeline` = text → solr_synonyms |
| CREATE TEXT SEARCH DICTIONARY | https://docs.serenedb.com/sql/statements/create_text_search_dictionary | шаблоны composition / text / synonyms |
| ts_lexize | https://docs.serenedb.com/sql/functions/search/full-text#ts_lexize | инспекция анализа |
| copy_from | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/copy-from | вариант с наследованием опций |

**ispell / hunspell** в доках SereneDB как шаблон словаря **не найден**
(`search_docs` по stemmer/snowball/ispell/synonyms). Штатная морфология —
**Snowball через `text`/`stem` + locale**.

---

## 2. Живые пробы на okna (до правки)

Сборка отвечает `PostgreSQL 18.3 (SereneDB 26.08.1)`.

| запрос | результат |
|---|---|
| `ts_lexize('search_dict_stem','клиент'/'клиенты'/'клиентов'/'клиента'/'клиентам')` | все → **`{клиент}`** |
| `ts_lexize('search_dict_stem','продажа'/'продажи')` | оба → **`{продаж}`** |
| `ts_lexize('search_dict_stem','продали')` | **`{прода}`** ← Snowball не сводит с «продажа» |
| `ts_lexize('search_dict_syn','клиенты')` | класс с «клиенты» |
| `ts_lexize('search_dict_syn','клиент'/'клиентов')` | passthrough, связи нет |

Пробный pipeline `text(stem=true, ru_RU)` → `solr_synonyms` с **стем-ключами**
(`клиент, контрагент, поставщик`): все падежи «клиент*» дают один класс.
Тот же pipeline с ключом-поверхностью «клиенты» — **не** срабатывает
(после стемма ключ не находится).

**Находка:** `search_dict_stem` (`copy_from` от `search_dict`) для `ts_lexize`
работает, но на **inverted-индексе** `tfidf(...)=0`. Нужен словарь с явным
`frequency=true` (иначе ранжирование ломается).

---

## 3. Что сделано (штатно, внутри базы)

### 3.1 Бэкап

```sql
CREATE TABLE search_entity_alias_c3_snap_20260827 AS
  SELECT * FROM search_entity_alias;  -- 257
CREATE TABLE search_dict_syn_bak_c3_20260827 (k VARCHAR, v VARCHAR);
-- мета: dict до/после, меры
```

### 3.2 Индекс алиасов со стеммингом

```sql
CREATE TEXT SEARCH DICTIONARY search_dict_alias_stem (
  template = 'text', locale = 'ru_RU.UTF-8', case = 'lower',
  stemming = true, accent = false,
  frequency = true, position = true, norm = true);

DROP INDEX IF EXISTS alias_idx;
CREATE INDEX alias_idx ON search_entity_alias
  USING inverted(aliases search_dict_alias_stem, src_table)
  INCLUDE (src_table);
GRANT SELECT ON alias_idx TO serene_ro;
VACUUM (REFRESH_TABLE) search_entity_alias;
```

### 3.3 `search_dict_syn`: pipeline + стем-ключи

Ключи карты — **стемы одиночных** слов из `search_entity_alias.aliases`
через `ts_lexize('search_dict_stem', …)` (многословные алиасы в карту не
кладутся: иначе «список»/«партнер» раздули бы класс). **18** правил.
Список слов руками не писался.

```sql
CREATE TEXT SEARCH DICTIONARY search_dict_syn (
  template = 'pipeline',
  step1_template = 'text',
  step1_locale = 'ru_RU.UTF-8',
  step1_case = 'lower',
  step1_stemming = true,
  step2_template = 'solr_synonyms',
  step2_synonyms = '<stem rules…>'  -- в т.ч. «клиент, контрагент, поставщик»
);
```

---

## 4. Мера до / после (те же 23 q okna-gold)

Прибор: формула `alias_rank_bench` (`aliases @@ вопрос`, `tfidf`, эталон =
`src_table` из gold). Модель не зовётся.

| | эталон лидер | в тройке | не найден | из |
|---|---:|---:|---:|---:|
| **ДО** (`search_dict`, поверхность) | **0** | **1** | **21** | 23 |
| **ПОСЛЕ** (`search_dict_alias_stem` + morph syn) | **3** | **0** | **19** | 23 |

Стали лидерами:

- «сколько у нас всего клиентов?» → `catalog_контрагенты`
- «сколько клиентов реально покупают?» → `catalog_контрагенты`
- «сколько документов реализации за декабрь 2025?» → `document_реализациятмц`

Большинство вопросов про «продали» по-прежнему мимо: Snowball даёт
`продали→прода`, а в алиасах стем `продаж` — это ограничение стеммера, не
повод для своего нормализатора.

---

## 5. Токен-пробы после починки

### `ts_lexize('search_dict_syn', …)`

| терм | toks |
|---|---|
| клиент | `{клиент,контрагент,поставщик}` |
| клиента | `{клиент,контрагент,поставщик}` |
| клиентов | `{клиент,контрагент,поставщик}` |
| клиентам | `{клиент,контрагент,поставщик}` |
| клиенты | `{клиент,контрагент,поставщик}` |
| продажа | `{продаж}` (класса ≥2 стем-слов у продаж в карте нет) |
| продажи | `{продаж}` |
| номенклатура | `{вид,номенклатур}` |

### `aliases @@` по `alias_idx` (лидер tfidf)

| терм | топ |
|---|---|
| клиент / клиента / клиентов / клиенты | **`catalog_контрагенты`** (+соседи с тем же стемом) |
| продажа / продажи | `accumulationregister_книгапродаж`, …`реализациятмц` |
| номенклатура | `catalog_видыноменклатуры`, **`catalog_номенклатура`**, … |

---

## 6. Откат

```sql
DROP INDEX IF EXISTS alias_idx;
CREATE INDEX alias_idx ON search_entity_alias
  USING inverted(aliases search_dict, src_table) INCLUDE (src_table);
GRANT SELECT ON alias_idx TO serene_ro;
VACUUM (REFRESH_TABLE) search_entity_alias;
-- search_dict_syn: python3 solr_synonyms_build.py compile --dsn "$DSN" --apply
-- (вернёт bare solr_synonyms с поверхностной картой)
-- снимок строк: search_entity_alias_c3_snap_20260827
```

---

## 7. Риски / долг

1. **`corpus_init.sql`** всё ещё создаёт `alias_idx` на `search_dict`
   (без стемма). Следующий такт сборки корпуса **сотрёт** морфологию индекса,
   пока init не переведён на `search_dict_alias_stem` (или равный).
2. **`solr_synonyms_build.py compile --apply`** пишет bare `solr_synonyms`
   без pipeline/stem-ключей — тоже откатит `search_dict_syn`.
3. Snowball ≠ полная морфология: «продали» ≠ «продажа»; ispell в движке нет.

---

## Вывод

Штатная морфология **есть** (Snowball `ru_RU`) и на живой сборке **работает**.
Блокер «человек пишет „клиентов“, словарь знает „клиенты“» снят для
`ts_lexize` и для `@@` по алиасам. Мера лидеров на 23 q: **0 → 3**.
Закрепить в init/компиляторе словаря — отдельный шаг (иначе живой фикс
временный).
