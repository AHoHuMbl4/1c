# Ф6 / §7bis — аудит хардкода (красная линия §Ф6.6)

**Дата:** 25.08.2026  
**Критерий:** на чужой базе (другая конфигурация 1С, язык, набор данных) код
работает без правки кода и без ручного разбора. Нужное знает движок / `$metadata`
/ модель / словарь в данных — спросить их, а не носить список слов.  
**Коммиты:** `e400657`, `5c22a72`, `1da0003`, `b8f30aa`, `8a43d2f`, `a67eec7`
(+ чтение `ASK_SQL_RRF` / резолвер-файлов из списка задачи).  
**Режим:** офлайн; живой прогон и LLM не использовались.

## Что проверено

| Объект | Как |
|---|---|
| `ubuntu/serenedb/solr_synonyms_build.py` | целиком + grep кириллицы / LIMIT / списков |
| `ubuntu/serenedb/build.sh` (7-solr и env `SOLR_SYN_*`) | дифф `b8f30aa`/`a67eec7` |
| `ubuntu/serenedb/corpus_init.sql` (solr_synonyms + `search_calendar_map`) | блок Ф6.3 / §7bis |
| `ubuntu/serenedb/corpus_build.sql` (§1-кватер календарь) | дифф `b8f30aa` |
| `ubuntu/serenedb/corpus_precheck.sql` (Ф6.3) | дифф `b8f30aa` |
| `ubuntu/serenedb/build_resolver_index.py` | целиком (в диффах Ф6 **нет**) |
| `ubuntu/serenedb/measure_resolver.py` | целиком (в диффах Ф6 **нет**) |
| `ubuntu/serenedb/resolver_build.sql` | целиком (такт; в диффах Ф6 **нет**) |
| `ubuntu/serenedb/serene_ask.py` | **только чтение**; диффы `e400657`/`5c22a72`/`8a43d2f` + флаги SQL_RRF |
| Замки | `test_solr_synonyms_*`, `test_build_solr_synonyms`, `test_calendar_*`, `test_resolver_ivf`, `test_health_native_freshness`, `test_sql_rrf`, новый `test_measure_resolver_terms` |

Доки SereneDB при аудите: `search_docs` →
`sql/statements/create_text_search_dictionary/solr-synonyms` (карта синонимов —
inline из данных, не из кода).

## Таблица находок

| # | файл:строка | что привязывает | вердикт |
|---|---|---|---|
| 1 | `measure_resolver.py` (бывш. `TERMS = ["спб", "питере", …]`) | Список городов/термов конкретной базы в исполняемом коде стендового замера | **починено** — термы только из `argv`; без аргументов usage+код 2; замок `test_measure_resolver_terms.py` **4/0** |
| 2 | `solr_synonyms_build.py:29-30` `MAX_RULES`/`MAX_BYTES` | Числовые потолки карты | **законно**: бюджет движка по живому замеру `F6_SYNONYMS_FACTS` §3.2; сверх лимита — `LimitError`, тихой обрезки нет (п. 13) |
| 3 | `solr_synonyms_build.py` | Имена `search_entity_alias` / `search_dict_syn` | **законно**: имена **наших** служебных таблиц/словаря (контракт корпуса), не сущностей 1С; override через env/`--alias-table`/`--dict`. Слот `search_synonym_bridge` снят (С3) |
| 4 | `corpus_build.sql` §1-кватер (~164–370) | `informationregister_%`, `chartofcharacteristictypes_%`, `Ref_Key`, `Description`, `*_Key`, `Edm.*` | **законно**: префиксы и поля **платформенного** OData 1С из `$metadata` / витрины; имён конфигурации («Календарь», «ДниНедели», «Рабочий») в SQL нет (замок meta **30/0**) |
| 5 | `corpus_build.sql` §1-кватер `ORDER BY prop LIMIT 1` | Выбор колонки даты/ключа/часов при нескольких кандидатах | **законно**: стабильный структурный выбор, затем уточнение join-ом витрины (`tmp3_cal_keyhits` / `besthour`); не список слов и не имя сущности |
| 6 | `corpus_init.sql` / `build.sh` / precheck Ф6.3 | Пустая заготовка `solr_synonyms`, `SOLR_SYN_DICT` из env | **законно**: словарь наполняется из таблиц (`solr_synonyms_build`); имя не имя базы клиента |
| 7 | `resolver_build.sql:63-64` | `DataVersion`, `PredefinedDataName`, `%_Base64Data` | **законно**: спутники протокола OData 1С (не реквизиты конфигурации); отбор по структуре, без кардинальных отсечек |
| 8 | `build_resolver_index.py` | Устаревший путь; комментарии «питер»/city | **законно (вне такта)**: такт зовёт только `resolver_build.sql` (`build.sh`); питон не в диффах Ф6; исполняемых списков сущностей нет |
| 9 | `serene_ask.py` Ф6.2/Ф6.3/Ф6.4 / SQL_RRF | IVF / `ts_lexize(dict)` / `sdb_metrics` / RRF — имена индексов из env | **законно** (чтение): списков слов/сущностей в добавленном коде нет; словарь и meta — из БД |
| 10 | `serene_ask.py:1654-1656` (`calendar_map_rows`, §7bis) | Распознавание `"не существует"` в тексте ошибки движка рядом с en | **требует правки serene_ask.py — оставлено оркестратору**: не список данных, но привязка к локали сообщения; достаточно en/`Catalog Error` как в `solr_synonyms_build.py` |
| 11 | `corpus_build.sql` §1-тер `accumulation_warehouse` | было: `IN ('quantity', 'количество')` | **починено** — отбор по `p.edm IN (Edm.Double/Decimal/Int*)` + Period, без языковых имён; `LineNumber`/`SurrogateKey` вне ресурса; диагностика `balance_map` rows_n; замок `test_balance_map_meta_build.py` **18/0**; okna: старое 3 ⊂ новое 13 |
| 12 | тесты `test_calendar_*`, `test_solr_*`, `test_resolver_ivf` | Кириллица в фикстурах / негативный grep «Календарь» / TRIG | **законно**: шапка замка; TRIG **запрещает** триггеры в calendar-хелперах ask |

## Итог

| | |
|---|---|
| Находок в таблице | **12** |
| Починено | **2** (`measure_resolver.py`, `corpus_build` §1-тер #11) |
| Законно | **9** |
| Оставлено оркестратору (`serene_ask`) | **1** (#10) |

**Самая опасная находка (до правки):** список городов стенда в `measure_resolver.py` —
исполняемый перечень значений конкретной базы; на чужой базе замер молча мерял бы не то.

**Пустой результат по диффам Ф6 production-пути:** в добавленном коде словаря
синонимов, карты календаря, IVF-резолвера, native freshness и SQL-RRF **имён
сущностей/счетов и языковых списков слов данных нет** — слова живут в alias /
`search_meta`/`search_calendar_map` либо приходят из `$metadata`.

## Замки (офлайн, 25.08)

| тест | результат |
|---|---|
| `test_measure_resolver_terms.py` | **4/0** |
| `test_solr_synonyms_build.py` | **28/0** |
| `test_solr_synonyms_apply.py` | **14/0** |
| `test_build_solr_synonyms.py` | **26/0** |
| `test_calendar_meta_build.py` | **30/0** |
| `test_calendar_axis.py` | **36/0** |
| `test_resolver_ivf.py` | **18/0** |
| `test_health_native_freshness.py` | **32/0** |
| `test_sql_rrf.py` | **7/0** |
| `test_balance_map_meta_build.py` | **18/0** |

Сумма: **213/0** (195+18).

## Правки этого захода

- `ubuntu/serenedb/measure_resolver.py` — термы из argv
- `ubuntu/serenedb/test_measure_resolver_terms.py` — оффлайн-замок
- `ubuntu/serenedb/corpus_build.sql` §1-тер — warehouse по Edm numeric (находка #11)
- `ubuntu/serenedb/test_balance_map_meta_build.py` — оффлайн-замок #11
- `docs/F6_HARDCODE_AUDIT.md` — этот отчёт
- `memory_bank/mcp-memory.json` — наблюдения с источником

`serene_ask.py` / `wiki_alias.sh` / запрещённый список документов задачи — **не трогались**.
