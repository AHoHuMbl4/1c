# 11. sales

## Зачем участок нужен
Участок — набор функций выбора источника и меры для вопросов про продажи (сумма/оборот/ранг) и смежного «прайс/номенклатура». Он решает: считать ли вопрос продажными (`sales_sum_intent`), поднять ли `accumulationregister_*` по `written_by` документа (`prefer_entity_for_sales`), какую меру взять — деньги или количество — и снять sticky-focus с неканона. Текст топ-K групп собирает `rank_groups_answer_text`.

## Входы
- `intent`: поля `want`, `kind`, `measure`, `amount` (`op`/`value`), `period` (`from`/`to`) — `ubuntu/serenedb/serene_ask.py:5244-5247`, `5349`, `5367`, `5635`, `5713`.
- `question` (строка), `plan` (`compute`), `cands` (список `src_table`), `agg` (`grain`/`groups`), `diag` (`sales_canon_locked`, `sales_canon_override`, `focus`), `trusted`/`resolved`/`focus`, `names`/`alias_by` мер, `locked`/`picked`/`arb_pool`/`doubt`, `act`, `grain_dec`, `prov_axis`.
- Константы модуля: `TABLES`=`search_tables` (`:77`), `ROWS_TO_MODEL` (`:118`), `UNIT_UNKNOWN` (`:7489`), `ASK_SALES_RANK_CANON` (`:1426`), опционально `serene_axis.rank_k` (`:5386-5391`).
- Env: только `ASK_SALES_RANK_CANON` читается в участке через модульную константу; `ASK_ROWS_TO_MODEL` — через `ROWS_TO_MODEL`.

## Порядок работы
1. **Детектор продаж** `sales_sum_intent` (`:5240`): сток/прайс → False; иначе sale по тексту/`kind`/`measure` или compare_period (лучше/хуже + неделя/месяц без HR) → True при `want`∈{sum,count,list,""} или `want`≠avg.
2. **Скоринг регистра** `_sales_register_score` (`:5271`): +10 qty, +3 всего/сумма, −4 НДС без qty, −8 книга/ндс в имени, +2 реализац/продаж.
3. **Lift возможен?** `sales_lift_possible` (`:5289`): в cands уже не-книга AR, иначе SQL parent/written_by → docs → SQL AR по written_by.
4. **Gate rank×sales** `sales_rank_engaged` (`:5336`): `ASK_SALES_RANK_CANON` ∧ `rank_intent_from` ∧ strong (sum|текст ранга|max/min|amount без op) ∧ `sales_lift_possible`.
5. **K** `_sales_rank_top_n` (`:5362`): amount.value 1…ROWS → топ-N в тексте → «лучших»+«три»→3 → max/min→1 → `serene_axis.rank_k` → иначе 1.
6. **Канон источника** `prefer_entity_for_sales` (`:5428`): без sum и без rank_gate → cands без изменений; иначе docs из cands+parent+written_by → lift AR; если пусто и `allow_cold` (умолч. not rank_gate) — cold все AR с written_by document_*, сортировка по score, порог ≥8 или ≥2+имя реализац/продаж/sale; сортировка lifted, `canon=lifted[0]`, docs и demote_regs убраны из пула, canon первым.
7. `sales_canon_src` (`:5534`): тот же gate; после prefer — первый, если `accumulationregister_*`, иначе None.
8. **Меры**: `sales_money_measure` (`:5549`) — `_fork_sum_headline_pool` или имя с всего/сумм/… без колич/себестоим; `sales_qty_measure` (`:5572`) — колич/qty/шт без сумм/всего; `sales_rank_canon_measure` (`:5625`) — measure_choice по word → money по алиасу в вопросе → qty при `_sales_product_rank_qty` → (None,None); `sales_force_money_measure` (`:5654`) — False при rank_canon∧rank_intent или фразах «что/какой продавалось»/лидер; иначе True при sum_intent.
9. **Пул/диаг**: `sales_canon_force_pool` (`:5677`) при locked → ([locked],[locked],False); `sales_canon_engaged` (`:5688`) — locked | override.стало | AR-focus не noncanon; `_zero_period_not_missing` (`:5708`) — empty_period/drop_assumed или sum+canon+period from/to.
10. **Sticky** `sales_refuse_sticky_focus` (`:5738`): sum без ticket_hatch; если sticky≠canon и sticky noncanon → focus=None, чистка memory/resolved.src, diag cleared.
11. **Прайс** `prefer_entity_for_catalog_count`/`catalog_count_src` (`:5789-5830`): want count/"" + прайс/номенклатур без прода/куп/остат → catalog товара в голову.
12. Вспомогательные: `period_zero_why_question` (`:5833`), `grain_dec_from_axis_ticket` (`:5846`), `_rank_wants_quantity`/`rank_measure_hint` (`:5855-5889`). С `:5892` — константы баланса (`_BALANCE_*`, `_STOCK_MARKERS`), не sales-логика.

## Выходы
- Переупорядоченный `cands` / `canon` src — потребители вне участка: `:12154-12155`, `:12581-12582`, `:13150-13205`, `:13841-13847`.
- Мера `_sm`/`how` — выбор меры `:13994-14024` (`sales_rank_canon_measure` / `sales_force_money_measure` / money|qty).
- `(focus, trusted, resolved, cleared)` — `:12671`; `(picked, arb_pool, doubt)` — `:13205`, `:13299`.
- Текст топ-K — `rank_groups_answer_text` (`:5397`), зов `:5132`.
- Bool/None для period_empty / no_data — `_zero_period_not_missing` `:14377+`, `sales_canon_engaged` в `:11212+`.

## Обращения наружу
Только `psql` (нет HTTP, нет вызова LLM в этом диапазоне):
| Место | SQL | Назначение |
|---|---|---|
| `:5303-5305` | `SELECT src_table, parent, written_by FROM search_tables WHERE src_table IN (…)` | docs для lift |
| `:5327-5330` | `SELECT src_table … accumulationregister_% AND written_by IN (…)` LIMIT 1 | есть ли lift |
| `:5446-5448` | тот же SELECT parent/written_by | карта parent/writer |
| `:5470-5473` | AR по written_by docs | список lifted |
| `:5482-5485` | все AR с `written_by LIKE 'document_%'` | cold-lift |
| `:5502-5503` | `SELECT written_by … src_table=cold[0]` | дописать docs |
| `:5490`, `:5512` | через `_measures_by_src` → SQL по `search_corpus` nums (`:3985`) | score регистров |
| `:5804-5808` | catalog_% с номенклатур/nomencl/товар/product LIMIT 24 | прайс-канон |

## Переключатели
- `ASK_SALES_RANK_CANON`: env `"0"` умолч., True только при `"1"` (`:1426`); читается в `sales_rank_engaged` (`:5343`), docstring prefer (`:5435`), `sales_force_money_measure` (`:5661`).
- `allow_cold` у prefer: умолч. `not rank_gate` (`:5443-5444`) — при rank_gate cold выкл.
- `ROWS_TO_MODEL` (env `ASK_ROWS_TO_MODEL`, умолч. 25) — потолок K и топ-N (`:5370`, `:5408`).

## Развилки
- Не sales_sum и не rank_gate → prefer/canon_src не меняют пул / None.
- Lift пуст → исходные cands; cold только если allow_cold и score/имя проходят порог (`:5497-5500`).
- Money vs qty: force_money True → money; product-rank/«что продавалось» → qty; rank_canon_measure: role_choice / role_ask / sales_money_role / sales_qty_canon / (None,None).
- Sticky: ticket_hatch (`decision_id` без from_memory, `:5718`) или sticky==canon или sticky уже канон-AR → не чистить.
- `sales_noncanon_focus` (`:5727`): AR с книга/ндс/vat → noncanon; всё не-AR → noncanon.
- Catalog: нет cats / не count / нет прайс-слов → без изменений.

## Чего здесь нет
- Нет агрегации/чтения фактов продаж из корпуса (только метаданные `search_tables` / меры через `_measures_by_src`).
- Нет HTTP и вызова языковой модели.
- Нет определения `sales_compare_*` (они выше, `:2025+`); нет `sales_period_empty` / fork-блоков (ниже, `:11208+`).
- Нет записи в БД; нет разбора OData.
- Строки `:5892-5898` — маркеры остатка/склада, не функции sales.
