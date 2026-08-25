# Ф6.6 — инвентарь языковых литералов в `serene_ask.py`

**Дата:** 25.08.2026  
**Объект:** `ubuntu/serenedb/serene_ask.py` (только чтение; код ask не менялся).  
**Критерий:** TARGET.md п. 9; `docs/HOW_NOT_TO.md` §0 / языковой хардкод; красная линия Ф6.6 в `docs/PLAN_UPGRADE_NATIVE.md`.  
**Не дублирует** 12 находок `docs/F6_HARDCODE_AUDIT.md` — здесь полный снимок литералов ask.

## Метод

1. `tokenize` + `ast.literal_eval` по файлу — все строковые литералы.
2. В инвентарь: литерал с кириллицей **или** языковой/конфигурационной привязкой
   в NL-матчерах (en-маркеры `sold`/`sales`/`top`…, `LIKE %%номенклатур%%`,
   `catalog_номенклатура`, маркеры остатков).
3. Классы:
   - **DATA** — должно жить в таблице/словаре/мете, не в коде;
   - **UI** — текст человеку (разрешённые через env `ASK_NO_DATA_TEXT` /
     `ASK_TOTAL_TEXT`, плюс дефолт `ASK_STALE_TEXT` и прочие уточнения/отказы);
   - **PROTO** — платформенный OData/1С (`document_`…) или перевод вида платформы
     (`_KIND_WORD`) / локаль ошибки движка (`не существует`);
   - **FALSE** — docstring, diag/journal, operator/log, колонки наших таблиц
     (`search_coverage`), не NL-привязка.
4. Замок не писался: правка ask запрещена этим прогоном.

## Числа

| класс | N |
|---|---:|
| DATA | **265** |
| UI | **26** |
| PROTO | **31** |
| FALSE | **586** |
| **всего в инвентаре** | **908** |

FALSE из них: docstring ≈ **380**, прочее (diag/log/исключения/контракт корпуса) ≈ **206**.

### DATA из сегодняшних коммитов rank / K5

Источник: `git show -U0` по `ubuntu/serenedb/serene_ask.py` за
`7ba1946` (Rank-путь / `ASK_SALES_RANK_CANON`) и `9d6d788` (K5 / `ASK_ATOM_TERMINAL`).
Считались только **новые** строковые литералы с кириллицей или явные NL-маркеры
en в тех же добавленных списках (`sold`/`top sell`/…). Ключи JSON (`leader`),
имена флагов и PROTO-префиксы (`document_`) не входят в DATA.

| коммит | вхождений DATA (net-new) | вхождений FALSE (net-new) | примечание |
|---|---:|---:|---|
| `7ba1946` rank | **34** (27 кир. + 7 en NL) | 0 | `_sales_rank_top_n`, `rank_question_text`, `_sales_product_rank_qty` |
| `9d6d788` K5 | **0** | 2 | `исход unique→ответ`, `mute computed→ответ` (diag) |
| **итого DATA сегодня** | **34** | | уникальных строк **30** |

Уникальные DATA, добавленные сегодня:

- `лучших`
- `лучший`
- `лучшие`
- `лучшего`
- `лучшая`
- `(?:топ|top)\s*-?\s*(\d+)`
- `\b(\d+)\s*(?:лучш|best)\b`
- `три `
- `трое `
- `трёх `
- `трех `
- `лучше всего`
- `хуже всего`
- `топ продаж`
- `лидер продаж`
- `что `
- `что`
- `какой `
- `какая `
- `какие `
- `продава`
- `продало`
- `продали`
- `best sell`
- `top sell`
- `most sold`
- `which `
- `what `
- `sold`
- `sales`

Типичные: «лучших» / «три » / «трёх » в `_sales_rank_top_n`; фразы
`_sales_product_rank_qty` («топ продаж», «какой », «продава»…).
K5 языковых DATA не добавил.

### DATA по функциям (сводка)

| функция | N |
|---|---:|
| `sales_sum_intent` | 35 |
| `rank_question_text` | 27 |
| `sales_compare_intent` | 23 |
| `_fork_word_names_measure` | 18 |
| `_sales_product_rank_qty` | 17 |
| `sales_force_money_measure` | 17 |
| `prefer_entity_for_catalog_count` | 15 |
| `rank_measure_hint` | 14 |
| `period_zero_why_question` | 13 |
| `_sales_rank_top_n` | 10 |
| `_sales_register_score` | 8 |
| `_rank_wants_quantity` | 8 |
| `prefer_entity_for_rank` | 6 |
| `sales_money_measure` | 6 |
| `sales_qty_measure` | 6 |
| `_is_product_catalog` | 6 |
| `_is_price_list_noise` | 5 |
| `_fork_headline_measure` | 4 |
| `total_question_skips_axis` | 3 |
| `stock_balance_is_sales_noise` | 3 |
| `_resolve_values_literal` | 2 |
| `_shares_chars` | 2 |
| `_pick_sum_headline` | 2 |
| `prefer_entity_for_sales` | 2 |
| `sales_canon_engaged` | 2 |
| `sales_noncanon_focus` | 2 |
| `<module>` | 2 |
| `_resolve_values_corpus` | 1 |
| `_ngrams` | 1 |
| `_fork_headline_doc_measures` | 1 |
| `_fork_sum_headline_pool` | 1 |
| `_with_doc_hdr` | 1 |
| `sales_refuse_sticky_focus` | 1 |
| `split_ident` | 1 |

## Таблица DATA

| файл:строка | литерал (≤80) | функция | класс |
|---|---|---|---|
| `ubuntu/serenedb/serene_ask.py:2005` | `лучше всего` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2005` | `лучше всех` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2005` | `хуже всего` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2005` | `хуже всех` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2006` | `больше всего` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2006` | `больше всех` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2006` | `меньше всего` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2006` | `меньше всех` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2007` | `leader` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2007` | `лидер` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2007` | `рейтинг` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2007` | `топ ` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2007` | `топ-` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2010` | ` чем` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2010` | `по сравнению` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2010` | `против` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2010` | `чем ` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2014` | `больше чем` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2014` | `лучше` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2014` | `меньше чем` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2014` | `хуже` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2015` | `больше, чем` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:2015` | `меньше, чем` | `sales_compare_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:3084` | `[^0-9a-zа-яё]` | `_resolve_values_literal` | DATA |
| `ubuntu/serenedb/serene_ask.py:3102` | `[0-9a-zа-яё]+` | `_resolve_values_literal` | DATA |
| `ubuntu/serenedb/serene_ask.py:3126` | `[^0-9a-zа-яё]` | `_resolve_values_corpus` | DATA |
| `ubuntu/serenedb/serene_ask.py:3211` | `[^0-9a-zа-яё]` | `_ngrams` | DATA |
| `ubuntu/serenedb/serene_ask.py:3221` | `[^0-9a-zа-яё]` | `_shares_chars` | DATA |
| `ubuntu/serenedb/serene_ask.py:3222` | `[^0-9a-zа-яё]` | `_shares_chars` | DATA |
| `ubuntu/serenedb/serene_ask.py:3506` | `документа` | `_fork_headline_doc_measures` | DATA |
| `ubuntu/serenedb/serene_ask.py:3519` | `всего` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3519` | `итог` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3519` | `колич` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3519` | `себестоим` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3519` | `стоим` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3519` | `сумм` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3519` | `цен` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3520` | `аванс` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3520` | `выруч` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3520` | `нацен` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3520` | `ндс` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3520` | `оборот` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3520` | `остат` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3520` | `скид` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3521` | `задолж` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3521` | `оплат` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3521` | `прибыл` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3521` | `убыт` | `_fork_word_names_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:3532` | `всего` | `_fork_sum_headline_pool` | DATA |
| `ubuntu/serenedb/serene_ask.py:3566` | `сумм` | `_with_doc_hdr` | DATA |
| `ubuntu/serenedb/serene_ask.py:4063` | `документа` | `_pick_sum_headline` | DATA |
| `ubuntu/serenedb/serene_ask.py:4069` | `всего` | `_pick_sum_headline` | DATA |
| `ubuntu/serenedb/serene_ask.py:4087` | `сумм` | `_fork_headline_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:4091` | `сумм` | `_fork_headline_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:4093` | `документа` | `_fork_headline_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:4099` | `всего` | `_fork_headline_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:4260` | `всего` | `total_question_skips_axis` | DATA |
| `ubuntu/serenedb/serene_ask.py:4260` | `итог ` | `total_question_skips_axis` | DATA |
| `ubuntu/serenedb/serene_ask.py:4260` | `итого` | `total_question_skips_axis` | DATA |
| `ubuntu/serenedb/serene_ask.py:4279` | `больше всего` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4279` | `больше всех` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4279` | `лучше всего` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4279` | `лучше всех` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4280` | `наибольш` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4280` | `наименьш` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4281` | `лучшая` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4281` | `лучшего` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4281` | `лучшие` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4281` | `лучший` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4281` | `лучших` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4282` | `какая номенклатур` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4282` | `какого товар` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4282` | `какой товар` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4283` | `leader` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4283` | `maximum` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4283` | `лидер` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4283` | `рейтинг` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4284` | `топ ` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4284` | `топ-` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4288` | `лучше` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4289` | `sales` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4289` | `sell` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4289` | `sold` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4289` | `продав` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4289` | `продаж` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4289` | `продал` | `rank_question_text` | DATA |
| `ubuntu/serenedb/serene_ask.py:4641` | `product` | `prefer_entity_for_rank` | DATA |
| `ubuntu/serenedb/serene_ask.py:4641` | `номенклатур` | `prefer_entity_for_rank` | DATA |
| `ubuntu/serenedb/serene_ask.py:4641` | `товар` | `prefer_entity_for_rank` | DATA |
| `ubuntu/serenedb/serene_ask.py:4642` | `product` | `prefer_entity_for_rank` | DATA |
| `ubuntu/serenedb/serene_ask.py:4642` | `номенклатур` | `prefer_entity_for_rank` | DATA |
| `ubuntu/serenedb/serene_ask.py:4642` | `товар` | `prefer_entity_for_rank` | DATA |
| `ubuntu/serenedb/serene_ask.py:4709` | `в прайсе` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4709` | `прайс` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4712` | `наторгова` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4712` | `наторговали` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4712` | `продаж` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4712` | `продал` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4712` | `продали` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4713` | `sales` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4713` | `sold` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4713` | `выручк` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4713` | `оборот` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4714` | `выруч` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4714` | `продаж` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4714` | `торг` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4716` | `sales` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4716` | `sold` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4716` | `наторговали` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4716` | `продаж` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4716` | `продал` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4716` | `продали` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4716` | `торги` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4718` | `больше чем` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4718` | `лучше` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4718` | `меньше чем` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4718` | `хуже` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4719` | `больше, чем` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4719` | `меньше, чем` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4720` | `квартал` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4720` | `месяц` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4720` | `недел` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4722` | `зарплат` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4722` | `отработ` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4722` | `сотрудник` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4722` | `табель` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4722` | `фота` | `sales_sum_intent` | DATA |
| `ubuntu/serenedb/serene_ask.py:4736` | `количество` | `_sales_register_score` | DATA |
| `ubuntu/serenedb/serene_ask.py:4738` | `всего` | `_sales_register_score` | DATA |
| `ubuntu/serenedb/serene_ask.py:4738` | `сумма` | `_sales_register_score` | DATA |
| `ubuntu/serenedb/serene_ask.py:4740` | `ндс` | `_sales_register_score` | DATA |
| `ubuntu/serenedb/serene_ask.py:4742` | `книга` | `_sales_register_score` | DATA |
| `ubuntu/serenedb/serene_ask.py:4742` | `ндс` | `_sales_register_score` | DATA |
| `ubuntu/serenedb/serene_ask.py:4744` | `продаж` | `_sales_register_score` | DATA |
| `ubuntu/serenedb/serene_ask.py:4744` | `реализац` | `_sales_register_score` | DATA |
| `ubuntu/serenedb/serene_ask.py:4835` | `(?:топ\|top)\s*-?\s*(\d+)` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4838` | `\b(\d+)\s*(?:лучш\|best)\b` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4841` | `лучшего` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4841` | `лучшие` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4841` | `лучший` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4841` | `лучших` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4842` | `трех ` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4842` | `три ` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4842` | `трое ` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4842` | `трёх ` | `_sales_rank_top_n` | DATA |
| `ubuntu/serenedb/serene_ask.py:4959` | `продаж` | `prefer_entity_for_sales` | DATA |
| `ubuntu/serenedb/serene_ask.py:4959` | `реализац` | `prefer_entity_for_sales` | DATA |
| `ubuntu/serenedb/serene_ask.py:5024` | `всего` | `sales_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5024` | `выруч` | `sales_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5024` | `оборот` | `sales_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5024` | `сумм` | `sales_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5025` | `колич` | `sales_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5025` | `себестоим` | `sales_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5038` | `единиц` | `sales_qty_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5038` | `колич` | `sales_qty_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5038` | `шт` | `sales_qty_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5039` | `всего` | `sales_qty_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5039` | `себестоим` | `sales_qty_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5039` | `сумм` | `sales_qty_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5075` | `лидер продаж` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5075` | `лучше всего` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5075` | `топ продаж` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5075` | `хуже всего` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5076` | `best sell` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5076` | `most sold` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5076` | `top sell` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5078` | `какая ` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5078` | `какой ` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5078` | `что` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5078` | `что ` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5079` | `какие ` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5080` | `sales` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5080` | `sold` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5080` | `продава` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5080` | `продали` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5080` | `продало` | `_sales_product_rank_qty` | DATA |
| `ubuntu/serenedb/serene_ask.py:5127` | `лидер продаж` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5127` | `лучше всего` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5127` | `топ продаж` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5127` | `хуже всего` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5128` | `best sell` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5128` | `most sold` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5128` | `top sell` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5130` | `какая ` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5130` | `какой ` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5130` | `что` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5130` | `что ` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5131` | `какие ` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5132` | `sales` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5132` | `sold` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5132` | `продава` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5132` | `продали` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5132` | `продало` | `sales_force_money_measure` | DATA |
| `ubuntu/serenedb/serene_ask.py:5155` | `sales_canon_locked` | `sales_canon_engaged` | DATA |
| `ubuntu/serenedb/serene_ask.py:5158` | `sales_canon_override` | `sales_canon_engaged` | DATA |
| `ubuntu/serenedb/serene_ask.py:5194` | `книга` | `sales_noncanon_focus` | DATA |
| `ubuntu/serenedb/serene_ask.py:5194` | `ндс` | `sales_noncanon_focus` | DATA |
| `ubuntu/serenedb/serene_ask.py:5222` | `было` | `sales_refuse_sticky_focus` | DATA |
| `ubuntu/serenedb/serene_ask.py:5235` | `установкацен` | `_is_price_list_noise` | DATA |
| `ubuntu/serenedb/serene_ask.py:5235` | `ценыноменклатур` | `_is_price_list_noise` | DATA |
| `ubuntu/serenedb/serene_ask.py:5236` | `informationregister_цены` | `_is_price_list_noise` | DATA |
| `ubuntu/serenedb/serene_ask.py:5237` | `номенклатур` | `_is_price_list_noise` | DATA |
| `ubuntu/serenedb/serene_ask.py:5237` | `цен` | `_is_price_list_noise` | DATA |
| `ubuntu/serenedb/serene_ask.py:5242` | `catalog_` | `_is_product_catalog` | DATA |
| `ubuntu/serenedb/serene_ask.py:5244` | `вид` | `_is_product_catalog` | DATA |
| `ubuntu/serenedb/serene_ask.py:5244` | `групп` | `_is_product_catalog` | DATA |
| `ubuntu/serenedb/serene_ask.py:5244` | `тип` | `_is_product_catalog` | DATA |
| `ubuntu/serenedb/serene_ask.py:5246` | `номенклатур` | `_is_product_catalog` | DATA |
| `ubuntu/serenedb/serene_ask.py:5246` | `товар` | `_is_product_catalog` | DATA |
| `ubuntu/serenedb/serene_ask.py:5256` | `в прайсе` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5256` | `номенклатур` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5256` | `прайс` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5258` | `куп` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5258` | `остат` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5258` | `прода` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5258` | `склад` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5265` | `SELECT src_table FROM %s WHERE src_table LIKE 'catalog_%%' ` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5266` | `AND (src_table LIKE '%%номенклатур%%' OR src_table LIKE '%%nomencl%%' ` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5267` | `OR src_table LIKE '%%товар%%' OR src_table LIKE '%%product%%') ` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5275` | `catalog_nomenclature` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5275` | `catalog_номенклатура` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5275` | `catalog_товары` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5276` | `catalog_goods` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5276` | `catalog_products` | `prefer_entity_for_catalog_count` | DATA |
| `ubuntu/serenedb/serene_ask.py:5298` | `зачем` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5298` | `ошибк` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5298` | `почему` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5298` | `сбой` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5299` | `нет продаж` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5299` | `ноль` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5299` | `нуле` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5299` | `нуль` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5300` | `продаж нет` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5301` | `воскресен` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5301` | `вчера` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5301` | `день` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5301` | `недел` | `period_zero_why_question` | DATA |
| `ubuntu/serenedb/serene_ask.py:5317` | `product` | `_rank_wants_quantity` | DATA |
| `ubuntu/serenedb/serene_ask.py:5317` | `номенклатур` | `_rank_wants_quantity` | DATA |
| `ubuntu/serenedb/serene_ask.py:5317` | `товар` | `_rank_wants_quantity` | DATA |
| `ubuntu/serenedb/serene_ask.py:5318` | `больше всего` | `_rank_wants_quantity` | DATA |
| `ubuntu/serenedb/serene_ask.py:5318` | `сколько` | `_rank_wants_quantity` | DATA |
| `ubuntu/serenedb/serene_ask.py:5319` | `leader` | `_rank_wants_quantity` | DATA |
| `ubuntu/serenedb/serene_ask.py:5319` | `maximum` | `_rank_wants_quantity` | DATA |
| `ubuntu/serenedb/serene_ask.py:5319` | `лидер` | `_rank_wants_quantity` | DATA |
| `ubuntu/serenedb/serene_ask.py:5334` | `maximum` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5334` | `больше всего` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5334` | `сколько` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5335` | `leader` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5335` | `лидер` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5336` | `количество` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5337` | `product` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5337` | `номенклатур` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5337` | `товар` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5338` | `количество` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5339` | `product` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5339` | `номенклатур` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5339` | `товар` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5340` | `количество` | `rank_measure_hint` | DATA |
| `ubuntu/serenedb/serene_ask.py:5356` | `на складе` | `<module>` | DATA |
| `ubuntu/serenedb/serene_ask.py:5356` | `остат` | `<module>` | DATA |
| `ubuntu/serenedb/serene_ask.py:5602` | `книгапродаж` | `stock_balance_is_sales_noise` | DATA |
| `ubuntu/serenedb/serene_ask.py:5604` | `актсверки` | `stock_balance_is_sales_noise` | DATA |
| `ubuntu/serenedb/serene_ask.py:5606` | `реализац` | `stock_balance_is_sales_noise` | DATA |
| `ubuntu/serenedb/serene_ask.py:6094` | `([a-zа-яё0-9])([A-ZА-ЯЁ])` | `split_ident` | DATA |

## Таблица UI

| файл:строка | литерал (≤80) | функция | класс |
|---|---|---|---|
| `ubuntu/serenedb/serene_ask.py:323` | `\n\n⚠ Данные могли устареть: последнее обновление из 1С было %d мин назад.` | `<module>` | UI |
| `ubuntu/serenedb/serene_ask.py:5585` | `Вопрос про остатки — уточните источник из списка ` | `balance_bridge_clarify` | UI |
| `ubuntu/serenedb/serene_ask.py:5586` | `(без разреза по складам/товарам, если не указано иное).` | `balance_bridge_clarify` | UI |
| `ubuntu/serenedb/serene_ask.py:6002` | `Не удалось проверить все прочтения вопроса. ` | `fork_outcome_c` | UI |
| `ubuntu/serenedb/serene_ask.py:6003` | `Повторите запрос.` | `fork_outcome_c` | UI |
| `ubuntu/serenedb/serene_ask.py:6014` | `Не удалось проверить все прочтения вопроса. ` | `fork_outcome_c` | UI |
| `ubuntu/serenedb/serene_ask.py:6015` | `Повторите запрос.` | `fork_outcome_c` | UI |
| `ubuntu/serenedb/serene_ask.py:10528` | `данные по %s` | `opts_hints` | UI |
| `ubuntu/serenedb/serene_ask.py:10530` | `в поиске с %s` | `opts_hints` | UI |
| `ubuntu/serenedb/serene_ask.py:10532` | `не в поиске %s` | `opts_hints` | UI |
| `ubuntu/serenedb/serene_ask.py:10801` | `За %s записей в выбранном периоде нет` | `format_period_empty_text` | UI |
| `ubuntu/serenedb/serene_ask.py:10803` | `За выбранный период записей нет` | `format_period_empty_text` | UI |
| `ubuntu/serenedb/serene_ask.py:10806` | `итог по «%s» — 0.00` | `format_period_empty_text` | UI |
| `ubuntu/serenedb/serene_ask.py:10808` | `количество — 0` | `format_period_empty_text` | UI |
| `ubuntu/serenedb/serene_ask.py:10810` | `вне периода в базе %s %s` | `format_period_empty_text` | UI |
| `ubuntu/serenedb/serene_ask.py:10814` | `ближайшие данные за %s` | `format_period_empty_text` | UI |
| `ubuntu/serenedb/serene_ask.py:10817` | `ближайшие данные с %s по %s` | `format_period_empty_text` | UI |
| `ubuntu/serenedb/serene_ask.py:10821` | `ближайшие данные за %s` | `format_period_empty_text` | UI |
| `ubuntu/serenedb/serene_ask.py:11435` | `значения из вопроса не найдены в данных` | `answer` | UI |
| `ubuntu/serenedb/serene_ask.py:12882` | `Не удалось проверить все прочтения вопроса. ` | `answer` | UI |
| `ubuntu/serenedb/serene_ask.py:12883` | `Повторите запрос.` | `answer` | UI |
| `ubuntu/serenedb/serene_ask.py:13656` | `уточните ось группы` | `answer` | UI |
| `ubuntu/serenedb/serene_ask.py:14002` | `уточните ось группы` | `answer` | UI |
| `ubuntu/serenedb/serene_ask.py:15112` | `База данных временно недоступна. Повторите запрос через минуту.` | `do_POST` | UI |
| `ubuntu/serenedb/serene_ask.py:15114` | `Языковая модель сейчас не отвечает. Повторите запрос через минуту.` | `do_POST` | UI |
| `ubuntu/serenedb/serene_ask.py:15116` | `Сервис временно недоступен. Повторите запрос через минуту.` | `do_POST` | UI |

## Таблица PROTO

| файл:строка | литерал (≤80) | функция | класс |
|---|---|---|---|
| `ubuntu/serenedb/serene_ask.py:1863` | `не существует` | `calendar_map_rows` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4062` | `document_` | `_pick_sum_headline` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4092` | `document_` | `_fork_headline_measure` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4660` | `document_` | `prefer_entity_for_rank` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4676` | `document_` | `prefer_entity_for_rank` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4692` | `document_` | `prefer_entity_for_rank` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4773` | `document_` | `sales_lift_possible` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4776` | `document_` | `sales_lift_possible` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4779` | `document_` | `sales_lift_possible` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4782` | `document_` | `sales_lift_possible` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4919` | `document_` | `prefer_entity_for_sales` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4922` | `document_` | `prefer_entity_for_sales` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4925` | `document_` | `prefer_entity_for_sales` | PROTO |
| `ubuntu/serenedb/serene_ask.py:4945` | `LIKE 'document_%%'` | `prefer_entity_for_sales` | PROTO |
| `ubuntu/serenedb/serene_ask.py:5237` | `document_` | `_is_price_list_noise` | PROTO |
| `ubuntu/serenedb/serene_ask.py:5395` | `не существует` | `balance_map_rows` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10381` | `справочник` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10382` | `документ` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10383` | `журнал документов` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10384` | `регистр накопления` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10385` | `регистр сведений` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10386` | `регистр бухгалтерии` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10387` | `регистр расчёта` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10388` | `план счетов` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10389` | `план видов характеристик` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10390` | `план видов расчёта` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10391` | `бизнес-процесс` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10392` | `задача` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10393` | `план обмена` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10394` | `константа` | `<module>` | PROTO |
| `ubuntu/serenedb/serene_ask.py:10395` | `перечисление` | `<module>` | PROTO |

## FALSE (сводка, без полного дампа docstring)

Всего FALSE = **586**. Полный дамп docstring (~380 шт.) в таблицу
не копируется — это не привязка к языку данных. Ниже — FALSE **вне** docstring
(≈ **206**): diag/journal, operator, SQL наших колонок, короткие ключи шагов.

| файл:строка | литерал (≤80) | функция | класс |
|---|---|---|---|
| `ubuntu/serenedb/serene_ask.py:358` | `psql не запущен: %s` | `psql` | FALSE |
| `ubuntu/serenedb/serene_ask.py:415` | `🔴 ЭМБЕДДЕР ОТДАЁТ ДРУГУЮ МОДЕЛЬ: просим «%s», получаем «%s». ` | `embed_model_live` | FALSE |
| `ubuntu/serenedb/serene_ask.py:416` | `Поиск по смыслу выключен — векторы несравнимы.\n` | `embed_model_live` | FALSE |
| `ubuntu/serenedb/serene_ask.py:419` | `эмбеддер не отвечает, поиск по смыслу выключен: %r\n` | `embed_model_live` | FALSE |
| `ubuntu/serenedb/serene_ask.py:682` | `ASK_EMBED_NATIVE: недопустимое EMBED_SECRET` | `_ensure_embed_secret` | FALSE |
| `ubuntu/serenedb/serene_ask.py:693` | `ASK_EMBED_NATIVE: не задан EMBED_HOST/EMBED_BASE_URL` | `_ensure_embed_secret` | FALSE |
| `ubuntu/serenedb/serene_ask.py:702` | `ASK_EMBED_NATIVE: секрет эмбеддера недоступен: %s` | `_ensure_embed_secret` | FALSE |
| `ubuntu/serenedb/serene_ask.py:729` | `ai_embed недоступен: %s` | `_embed_one_native` | FALSE |
| `ubuntu/serenedb/serene_ask.py:731` | `ai_embed вернул пустой ответ` | `_embed_one_native` | FALSE |
| `ubuntu/serenedb/serene_ask.py:735` | `ai_embed: битый JSON вектора` | `_embed_one_native` | FALSE |
| `ubuntu/serenedb/serene_ask.py:737` | `ai_embed: ожидали массив FLOAT` | `_embed_one_native` | FALSE |
| `ubuntu/serenedb/serene_ask.py:739` | `ai_embed: размерность %d, ожидали %d` | `_embed_one_native` | FALSE |
| `ubuntu/serenedb/serene_ask.py:793` | `эмбеддер ответил с попытки %d\n` | `embed_one` | FALSE |
| `ubuntu/serenedb/serene_ask.py:802` | `эмбеддер недоступен: %s` | `embed_one` | FALSE |
| `ubuntu/serenedb/serene_ask.py:1243` | `модель не вернула разбор вопроса` | `_one_intent` | FALSE |
| `ubuntu/serenedb/serene_ask.py:3037` | `rerank отработал: %d кандидатов, порядок %s\n` | `rerank` | FALSE |
| `ubuntu/serenedb/serene_ask.py:3039` | `изменён` | `rerank` | FALSE |
| `ubuntu/serenedb/serene_ask.py:3040` | `без изменений` | `rerank` | FALSE |
| `ubuntu/serenedb/serene_ask.py:3048` | `rerank НЕ ОТРАБОТАЛ (порядок остаётся прежним): %r\n` | `rerank` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5159` | `стало` | `sales_canon_engaged` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5160` | `стало` | `sales_canon_engaged` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5222` | `стало` | `sales_refuse_sticky_focus` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5435` | `AND map_extract_value(refs_map, 'ТМЦ') IS NOT NULL` | `balance_registers_with_goods` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5509` | `именованный товар не в баланс-источниках` | `stock_balance_named_no_data` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5583` | `Ѐ` | `balance_bridge_clarify` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5583` | `ӿ` | `balance_bridge_clarify` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5596` | `мост не принёс баланс-источник` | `balance_bridge_clarify` | FALSE |
| `ubuntu/serenedb/serene_ask.py:5647` | `есть другое прочтение` | `<module>` | FALSE |
| `ubuntu/serenedb/serene_ask.py:6067` | `часть прочтений не удалось посчитать` | `fork_outcome_c` | FALSE |
| `ubuntu/serenedb/serene_ask.py:6070` | `есть ветка без проверенной подписи` | `fork_outcome_c` | FALSE |
| `ubuntu/serenedb/serene_ask.py:6646` | `Этот вариант выбора больше недоступен. Задайте вопрос снова.` | `choice_error_response` | FALSE |
| `ubuntu/serenedb/serene_ask.py:6647` | `Срок выбора истёк. Задайте вопрос снова.` | `choice_error_response` | FALSE |
| `ubuntu/serenedb/serene_ask.py:6648` | `Этот вариант уже был выбран. Задайте вопрос снова.` | `choice_error_response` | FALSE |
| `ubuntu/serenedb/serene_ask.py:6649` | `Выбор не подходит к этому вопросу. Задайте вопрос снова.` | `choice_error_response` | FALSE |
| `ubuntu/serenedb/serene_ask.py:6650` | `Выбор принадлежит другому пользователю. Задайте вопрос снова.` | `choice_error_response` | FALSE |
| `ubuntu/serenedb/serene_ask.py:7480` | `Ѐ` | `format_measure_empty_pivot` | FALSE |
| `ubuntu/serenedb/serene_ask.py:7480` | `ӿ` | `format_measure_empty_pivot` | FALSE |
| `ubuntu/serenedb/serene_ask.py:7482` | `По «%s» нет значений ни в одной записи` | `format_measure_empty_pivot` | FALSE |
| `ubuntu/serenedb/serene_ask.py:7484` | `; есть ` | `format_measure_empty_pivot` | FALSE |
| `ubuntu/serenedb/serene_ask.py:7724` | `ask: перечень сущностей обрезан по бюджету промпта ` | `pick_entity` | FALSE |
| `ubuntu/serenedb/serene_ask.py:7725` | `(%d из %d, порядок по смыслу)\n` | `pick_entity` | FALSE |
| `ubuntu/serenedb/serene_ask.py:7744` | `ask DEGRADED: выбор сущности без модели (%s)\n` | `pick_entity` | FALSE |
| `ubuntu/serenedb/serene_ask.py:8565` | `%s (есть: %s)` | `one` | FALSE |
| `ubuntu/serenedb/serene_ask.py:8565` | `нет` | `one` | FALSE |
| `ubuntu/serenedb/serene_ask.py:8596` | ` · всего позиций: ` | `ensure_n_groups_named` | FALSE |
| `ubuntu/serenedb/serene_ask.py:8617` | ` · всего записей: ` | `ensure_count_named` | FALSE |
| `ubuntu/serenedb/serene_ask.py:8790` | `нераспознанное место: %s` | `formulation_flaws` | FALSE |
| `ubuntu/serenedb/serene_ask.py:8792` | `пустая формулировка` | `formulation_flaws` | FALSE |
| `ubuntu/serenedb/serene_ask.py:8796` | `незаполненное место: %s` | `formulation_flaws` | FALSE |
| `ubuntu/serenedb/serene_ask.py:8865` | `число %s набрано цифрами вместо места {%s}` | `copied_figures` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9347` | `%s: заявлено %s, в базе %s` | `check_claims` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9392` | `%s=%s названо не цифрами` | `claims_in_text` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9473` | `величина %s не названа цифрами` | `asked_figure_missing` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9483` | `отброшено %d — не названо в ответе` | `asked_figure_missing` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9491` | `групп %s — не названо в ответе` | `asked_figure_missing` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9807` | `утечка инструкции: %s` | `gate_out` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9886` | `ask CLARIFY GATE: числа вне вариантов: %s\n` | `clarify_say` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9958` | `SELECT в_1С, в_корпусе, объектов_витрины, coalesce(причина,'') ` | `_coverage_of` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9980` | `декларация 1С` | `_coverage_of` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9982` | `витрина (перепись)` | `_coverage_of` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9984` | `витрина` | `_coverage_of` | FALSE |
| `ubuntu/serenedb/serene_ask.py:9992` | `более полный слой (%s) новее корпуса` | `_coverage_of` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10050` | `витрина` | `_assemble_health_gap` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10050` | `корпус` | `_assemble_health_gap` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10061` | `витрина` | `_assemble_health_gap` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10061` | `корпус` | `_assemble_health_gap` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10085` | `SELECT entity, объектов_витрины, в_корпусе FROM search_coverage` | `_measure_health_gap` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10106` | `WHERE объектов_витрины > в_корпусе ` | `_real_corpus_object_gaps` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10107` | `  AND coalesce(причина,'') <> %s` | `_real_corpus_object_gaps` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10108` | `не опубликовано в индекс` | `_real_corpus_object_gaps` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10268` | `SELECT coalesce(sum(в_1С) FILTER (WHERE в_1С > 0), 0),` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10269` | `       coalesce(sum(в_корпусе), 0),` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10270` | `       coalesce(sum(в_1С - в_корпусе) FILTER (WHERE в_1С > в_корпусе), 0),` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10271` | `       count(*) FILTER (WHERE в_1С > 0 AND в_корпусе = 0),` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10272` | `       count(*) FILTER (WHERE в_1С = -1) FROM search_coverage` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10277` | `SELECT entity, в_1С, в_корпусе, причина FROM search_coverage ` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10278` | `WHERE в_1С > 0 AND в_1С > в_корпусе ORDER BY в_1С - в_корпусе DESC LIMIT %d` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10281` | `ask COVERAGE: перепись недоступна: %s\n` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10284` | `перепись недоступна` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10288` | `перепись пуста — такт ещё не считал полноту` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10321` | `ask COVERAGE GATE: числа вне переписи: %s\n` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10324` | `утечка инструкции: %s` | `_coverage_answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10511` | `SELECT entity, (в_1С - в_корпусе) FROM search_coverage ` | `opts_hints` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10512` | `WHERE entity IN (%s) AND в_1С > в_корпусе` | `opts_hints` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10797` | `Ѐ` | `format_period_empty_text` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10797` | `ӿ` | `format_period_empty_text` | FALSE |
| `ubuntu/serenedb/serene_ask.py:10811` | `записей` | `format_period_empty_text` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11156` | `catalog_self` | `axis_focus_plan` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11185` | `было` | `axis_focus_plan` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11185` | `стало` | `axis_focus_plan` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11185` | `ось` | `axis_focus_plan` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11332` | `шаги` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11350` | `разбор вопроса` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11451` | `отбор: буквально` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11511` | `отбор: смысл и синонимы` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11642` | `кандидаты собраны` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11735` | `отсев «не отвечает»` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11837` | `эмбеддер не ответил — порядок кандидатов без смысла` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:11887` | `вектор вопроса не посчитан — порядок кандидатов без смысла` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12086` | `детектор развилки` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12093` | `ask FORK: детектор не сработал: %s\n` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12105` | `канон продаж: fork excluded → period_empty (до выбора)` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12117` | `канон продаж: снят sticky focus` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12117` | `было` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12118` | `стало` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12131` | `сущность снята — осталась` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12132` | `было` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12132` | `осталось` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12149` | `focus был осью — уточнить держателя` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12167` | `было` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12167` | `стало` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12167` | `ось` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12168` | `focus был осью` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12200` | `выбор сущности сделан без модели` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12435` | `место_выбора` | `_probe` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12436` | `место_лидера` | `_probe` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12464` | `лидер` | `_alias_verdict` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12464` | `своё слово` | `_alias_verdict` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12598` | `было` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12598` | `стало` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12599` | `канон продаж` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12614` | `catalog_count_override` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12614` | `было` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12614` | `стало` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12615` | `канон прайса` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12617` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12621` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12638` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12648` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12700` | `круг арбитра` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12710` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12738` | `стоп2 соперники` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12742` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12754` | `catalog_count_locked` | `_checked` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12825` | `детектор исходов` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12846` | `канон продаж: fork excluded → period_empty` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12856` | `исход unique→ответ` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12860` | `исход A` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12868` | `исход B` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12874` | `исход C` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12925` | `почему` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12929` | `величины` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12966` | `число` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:12967` | `у_соперника` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13029` | `кандидаты` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13030` | `числа` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13035` | `кандидаты` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13040` | `mute computed→ответ` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13093` | `выбор` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13093` | `ответил` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13108` | `ответил` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13108` | `уточнение` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13193` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13233` | `стало` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13250` | `канон продаж: period_window_empty → period_empty` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13259` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13264` | `сущность выбрана` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13265` | `человек` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13265` | `модель` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13309` | `было` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13309` | `стало` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13309` | `величина` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13342` | `слово` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13342` | `подошли` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13435` | `было` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13435` | `стало` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13439` | `величина выбрана` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13515` | `слово` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13516` | `выбрано` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13516` | `покрывают` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13575` | `стало` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13575` | `ось` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13576` | `ось` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13829` | `посчитано базой` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13838` | `счёт` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13847` | `счёт` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13875` | `счёт` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13876` | `счёт` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13876` | `без_даты_отброшено` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13894` | `счёт` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13895` | `счёт` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:13895` | `вне_периода` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14075` | `утечка инструкции: %s` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14083` | `гейт исходящего` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14135` | `утечка инструкции: %s` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14154` | `ask GATE: числа вне данных: %s\n` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14232` | `ask ASKBACK GATE: числа вне данных: %s\n` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14237` | `catalog_count_locked` | `answer` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14388` | `утечка инструкции: %s` | `_gate_need` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14405` | `чего_нет` | `_need_clarify` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14406` | `почему` | `_need_clarify` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14546` | `сомнение` | `_journal_doubt` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14547` | `сомнение` | `_journal_doubt` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14690` | `ask_journal: текст вопроса попал в SQL` | `_insert_row` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14741` | `шаг` | `_answer_checked_core` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14741` | `достаточность до поиска` | `_answer_checked_core` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14753` | `счёт` | `_answer_checked_core` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14756` | `со_значением` | `_answer_checked_core` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14758` | `строк` | `_answer_checked_core` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14764` | `достаточность после счёта` | `_answer_checked_core` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14890` | `счёт` | `_build_ask_scope` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14899` | `величина` | `_build_ask_scope` | FALSE |
| `ubuntu/serenedb/serene_ask.py:14903` | `ось` | `_build_ask_scope` | FALSE |
| `ubuntu/serenedb/serene_ask.py:15123` | `FATAL: ASK_TOKEN не задан — сервис без авторизации отдавал бы ` | `main` | FALSE |
| `ubuntu/serenedb/serene_ask.py:15124` | `данные витрины кому угодно. Задайте токен в окружении.\n` | `main` | FALSE |
| `ubuntu/serenedb/serene_ask.py:15127` | `serene-ask на http://%s:%d  (поиск в SereneDB, схема в модель не уходит)\n` | `main` | FALSE |

## План выноса DATA (без правки ask в этом прогоне)

### Уже есть в дереве

| хранилище | что закрывает | путь |
|---|---|---|
| `search_entity_alias` | синонимы сущностей (wiki-alias) | `ubuntu/serenedb/corpus_init.sql` |
| `search_measure_alias` | алиасы величин | `ubuntu/serenedb/corpus_init.sql` |
| `search_synonym_bridge` | кэш моста синонимов | `ubuntu/serenedb/corpus_init.sql` |
| `search_dict_syn` + Solr map | query-side синонимы (Ф6.3) | `solr_synonyms_build.py` / такт 7-solr |
| `period_relative_forms` | относительные окна («прошлую неделю»…) | `search_meta` + файл `ubuntu/serenedb/period_relative_forms.json` |
| `search_meta` (`balance_registers`, calendar_*) | регистры/карта из `$metadata` | сборка корпуса |

Часть пути уже читает словари (`measure_choice` ← `search_measure_alias`,
`period_form_from_question` ← `period_relative_forms`). NL-списки rank/sales/fork
в коде **мимо** этих таблиц.

### Чего не хватает

1. **Словарь форм ранга / compare** (маркеры «лучших», «топ-», «больше всего»,
   «чем », «по сравнению», top-N числительные «три/трое/трёх») — нет таблицы;
   `period_relative_forms` по форме подходит (form_id → phrases), но заведён
   только под окна дат.
2. **Стемы мер для fork/rank** (`сумм`/`колич`/`выруч`/…) — частично пересекаются
   с `search_measure_alias`, но алиасы там полные слова подписи, не стемы матчера.
3. **Маркеры домена продаж/прайса/остатков** (`продаж`, `прайс`, `остат`,
   `на складе`, en/ro в `_STOCK_MARKERS`) — не в alias; на чужом языке ломаются.
4. **Привязки к именам конфигурации** (`catalog_номенклатура`,
   `informationregister_цены`, `LIKE %%номенклатур%%`) — красная линия Ф6.6;
   нужны meta/`$metadata`/alias, не литерал.
5. **Алфавитный класс `[а-яё]`** в токенизации — языковая привязка; вынос в
   настройку локали/мета или штатный tokenizer движка (отдельный шаг, не ask-hotfix).

### Порядок (следующий прогон, не этот)

1. Вынести rank/compare/top-N фразы в meta JSON по образцу `period_relative_forms`
   (или расширить тот же ключ новыми form_id) — без нового «выбирателя».
2. Стемы мер — либо колонка/таблица рядом с `search_measure_alias`, либо
   порождение из алиасов штатным `ts_lexize` (после проверки доков).
3. Config-имена (`номенклатур`/`цены`) — только из `search_entity_alias` /
   `$metadata`, списки в коде снять.
4. UI-дубли сверх `ASK_NO_DATA_TEXT`/`ASK_TOTAL_TEXT` — свести к env или
   оставить как локализуемые шаблоны одним слоём (отдельно от DATA).
5. `#10` из `F6_HARDCODE_AUDIT.md` (`не существует`) — PROTO/локаль движка;
   достаточно en/`Catalog Error` (уже отмечено аудитом).

## Связь с аудитом Ф6.6

Аудит `docs/F6_HARDCODE_AUDIT.md` смотрел диффы Ф6 и оставил ask #10 оркестратору.
Этот документ — полный инвентарь ask: основная масса DATA не из IVF/solr/calendar,
а из **rank/sales/fork phrase-lists** (в т.ч. сегодняшние `7ba1946` / частично K5).

## Запреты этого прогона (соблюдены)

- `ubuntu/serenedb/serene_ask.py` и `test_*.py` не менялись;
- контуры `:8091`/`:8092` не трогались;
- замок, требующий правки ask, не писался;
- CHANGELOG / activeContext / progress / hooks / TARGET — без правок.
