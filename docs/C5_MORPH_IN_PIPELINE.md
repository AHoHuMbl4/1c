# С5 — морфология словаря в пайплайне (27.08.2026)

База: **okna** (`gpu-erw:2202`). `serene_ask.py` не трогали.
Закрывает риск С3: следующий такт больше не откатывает морфологию.

---

## 1. Доки SereneDB (до правки SQL)

| Раздел | URL |
|---|---|
| Stemming and Stopwords | https://docs.serenedb.com/cookbook/search/stemming |
| Synonyms (pipeline text→solr) | https://docs.serenedb.com/cookbook/search/synonyms |
| pipeline | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/pipeline |
| text | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/text |
| solr_synonyms | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/solr-synonyms |
| stem | https://docs.serenedb.com/sql/statements/create_text_search_dictionary/stem |

Штатный путь — Snowball через `text`/`stem` + locale; списков слов в коде нет.

---

## 2. Что было (дефект)

С3 вручную собрал на okna:

- `search_dict_alias_stem` + `alias_idx` на нём;
- `search_dict_syn` = pipeline `text(stem)` → `solr_synonyms` со **стем-ключами**.

Но в репозитории оставалось:

- `corpus_init.sql`: `alias_idx` на `search_dict` (без стемма); заготовка syn — bare `solr_synonyms`;
- `solr_synonyms_build.py compile --apply`: DROP+CREATE bare `solr_synonyms` с **поверхностными** ключами.

Любой такт 7-solr / хвост `wiki_alias` откатывал живую починку.

---

## 3. Что сделано в пайплайне

### 3.1 `corpus_init.sql`

- `CREATE … search_dict_alias_stem` (`text`, locale из `:'dict_locale'`,
  `stemming=true`, `frequency=true`);
- `alias_idx` → `inverted(aliases search_dict_alias_stem, …)`;
- заготовка `:"solr_syn_dict"` → **pipeline** `text(stem)` → `solr_synonyms` (пустая карта);
- умолчание имени `\if :{?solr_syn_dict}` сохранено (Д4).

### 3.2 `solr_synonyms_build.py`

- ключи карты: только **одиночные** слова из `search_entity_alias`, стемы через
  `ts_lexize(search_dict_stem, …)` (один SELECT, без списков в коде);
- `render_ddl`: DROP+CREATE **pipeline** `step1_stemming=true` → `solr_synonyms`;
- после `--apply`: пересоздание `alias_idx` на `search_dict_alias_stem` +
  `VACUUM (REFRESH_TABLE)` (файл `alias_idx_stem_ensure.sql`).

Такт на пустой базе получает морфологию сам, без ручных шагов.

---

## 4. Живой прогон шага словаря на okna

Полный пересбор корпуса не запускали. Шаг:

`python3 solr_synonyms_build.py compile --dsn … --apply`
(17 правил / 726 байт, locale `ru_RU.UTF-8`).

| проверка | результат |
|---|---|
| `ts_lexize(…,'клиент'/'клиента'/'клиентов'/'клиенты')` | один класс `{клиент,контрагент,поставщик}` |
| `count(*) FROM alias_idx` | **257** |
| DDL словаря | `template=pipeline`, `step1_stemming=true` |

⚠️ На момент прогона файла `solr_synonyms_build.py` в `/opt/1c-mcp-reports/`
не было (WorkingDirectory юнита `1c-wiki-alias@`). Прогон — из `/tmp/c5-morph/`
после выкладки бинаря сессией. После merge в `origin/main` нужен обычный
выкат скрипта в `/opt/1c-mcp-reports/` (как у остальных файлов такта), иначе
юнит снова не найдёт компилятор.

---

## 5. Замок

`ubuntu/serenedb/test_morph_dict_pipeline.py` — **19/0**.

- OLD bare `solr_synonyms` + поверхностные ключи → morph-check **FAIL**;
- NEW pipeline + stem-ключи + `corpus_init` на `search_dict_alias_stem` → **PASS**;
- поверхность ≠ стем-карта (откат компилятора ловится).

Рядом обновлены `test_solr_synonyms_build.py` (**37/0**),
`test_build_solr_synonyms.py` (**29/0**).

---

## 6. Мера ранга (те же 23 q, формула `alias_rank_bench`)

| | эталон лидер | в тройке | не найден | из |
|---|---:|---:|---:|---:|
| **С3 ДО** (поверхность) | **0** | **1** | **21** | 23 |
| **С3 ПОСЛЕ** (ручная морфология) | **3** | **0** | **19** | 23 |
| **С5 после compile --apply** | **3** | **0** | **20** | 23 |

Лидеры те же, что у С3:

- «сколько у нас всего клиентов?» → `catalog_контрагенты`
- «сколько клиентов реально покупают?» → `catalog_контрагенты`
- «сколько документов реализации за декабрь 2025?» → `document_реализациятмц`

(У С3 в таблице «не найден 19» при 3+0+19=22 — арифметика строки С3;
здесь 3+0+20=23.)

---

## Вывод

Морфология закреплена в init + компиляторе такта. Повторный `compile --apply`
на okna **сохранил** стемминг (`клиент*` → один класс, `alias_idx` 257).
Замок краснеет на старой сборке и зелёный на новой.
