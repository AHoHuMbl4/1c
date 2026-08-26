# S3. Как система решает, что именно считать

## Коротко

После сбора кандидатов `src_table` путь в `answer` сначала переупорядочивает источники (ранг/продажи/прайс), при маркерах остатка отсекает чужие регистры или отдаёт `no_data`/`clarify`. При `FORK_DETECT` полный скан корпуса группирует живые источники в классы эквивалентности; при `ASK_ENTITY_FORM` возможен ранний ответ формой F (счёт по оси / дополнение каталога). Sticky-фокус с неканона продаж снимается; билет выбора фиксирует сущность/меру. Позже при нескольких прочтениях `resolve_fork_outcome` даёт A/B/C/unique/empty/unavailable. Если развилка не закрыла путь — выбирается мера (`measure_choice` / канон продаж), при ранге — ось GROUP BY и детерминированный топ. Уточнение с `options` пломбируется билетами; ответ человека гасит билет и пишется в процессную память сессии.

## Схема пути

1. **Отсев «остатки + именованный товар» до развилки** — нет capable/goods → `stock_balance_named_no_data` (`11920–11925`, `12565–12570`).
2. **Перестановка кандидатов** — `prefer_entity_for_rank` → `prefer_entity_for_sales` → `prefer_entity_for_catalog_count` (`12153–12155`); при остатках: noise-фильтр, structural, bridge-clarify (`12156–12181`).
3. **Ранний скан развилки** (`FORK_DETECT`, `len(cands)>1`) — пул ≤`ARBITER_MAX*4`, `fork_detector_scan` → `diag.fork` / `_fork_early` (`12571–12629`); SQL count/sums по `search_corpus`, классы по отпечатку атома (`4107–4378`).
4. **Форма F pre_entity** (`ASK_ENTITY_FORM`) — `try_entity_form_answer(..., when="pre_entity")`: один early-класс и одна форма → ответ-атом; иначе `None` (`12637–12651`, `2540–2567`).
5. **Снятие sticky / hold билета** — `sales_refuse_sticky_focus` (`12671`); `hold_settled_entity` (`12685`, `7264–7298`).
6. **Форма F после arb_pool** — тот же `try_entity_form_answer` без `when` (`13315–13320`): `distinct_axis` / `complement` / pick `structs[0]` (`2441–2532`).
7. **Исходы развилки** (`FORK_OUTCOMES`∧`FORK_DETECT`, пул>1 или window-fork или `_ef_early`) — повторный `fork_detector_scan` по `arb_pool` → `resolve_fork_outcome` → A/B/C/unique/unavailable (`13356–13473`, `6285–6334`, builders `6354–6614`).
8. **Мера на одиночном src** — `measure_pick`→`resolve_measure`; иначе sales: `sales_rank_canon_measure` / `sales_force_money_measure`→money|qty; иначе `measure_choice` (`13981–14024`, `6638–6691`).
9. **Ранг** — сброс axis-clarify (`count_`/`total_question_skips_axis`, `14202+`); `rank_axis_resolve` (LLM pick → hits → rerank); `rank_deterministic_answer` / fallback (`4979–5162`, `14584+`).
10. **Уточнение и память** — ответ с `options` → `seal_clarify`→`issue_decision` (`15693–15694`, `7027–7079`); повтор с `decision_id` → `consume_decision`→`accumulate_resolution` (`15434–15463`); тень `attach_memory_shadow` (`15695–15696`); опц. `_try_memory_apply` при `ASK_MEMORY_APPLY` (`15386–15387`, `15483`).

## Точки принятия решений

| Условие | Сворот |
|---|---|
| маркеры остатка + именованный товар, нет capable/goods / пустой пул после фильтров | `kind=no_data` (`6042–6049`, `12160–12167`) |
| остатки без имени, capable есть, hit пуст / пул пуст | `kind=clarify` bridge (`6103–6136`, `12172–12181`) |
| `sales_sum_intent` / `sales_rank_engaged` | lift `accumulationregister_*` по `written_by`, canon=первый scored (`5428–5534`, `5336–5343`) |
| `ASK_SALES_RANK_CANON`∧rank∧strong∧lift | топ-N + роль меры qty/money (`5362`, `5625–5651`) |
| `sales_force_money_measure` | True→деньги; False при product-rank/«что продавалось»→qty (`5654–5674`) |
| sticky focus ≠ sales-canon и noncanon | focus=None, чистка memory/resolved (`5738+`) |
| `ASK_ENTITY_FORM`: count+catalog+sales, не гейт A | F открыта; иначе закрыта (`2281–2305`) |
| product+окно / kind→catalog / иначе | complement / distinct_axis (`2478–2492`); pick только `[0]` (`2503–2506`) |
| early_classes>1 или form_n≠1 на pre_entity | F не отвечает (`2546–2549`) |
| `scan_error` / нет live / нет applicable | unavailable / empty (`6294–6303`) |
| uncounted cell | исход C (`6304–6311`) |
| 1 класс, 1 src / много src | unique / A (`6312–6316`) |
| ≥2 класса, все с label / без label | B (figures+options) / C unsigned (`6317–6334`, `6472–6614`) |
| B: нет лидера/`render` | падение в C (`13449–13458`) |
| `ASK_ATOM_TERMINAL`∧unique computed | ранний return unique (`13436–13445`) |
| `rank_intent_from` | детерминированный топ; иначе None (`5084–5090`) |
| 0/1/2+ осей | `(None,pool)` / одна / лидер+alts (`4979–5041`) |
| `seal_clarify`: kind∈{clarify,figures,answer} и options | билеты в `_DECISIONS` (`7034–7079`) |
| `consume_decision` err | reissue batch или fallback без trusted (`15436–15454`) |
| ticket ok | focus/measure из ticket, `trusted`, accumulate (`15455–15463`) |

## Что участвует снаружи

- **Таблицы SereneDB:** `search_corpus` (скан/меры/ТМЦ), `search_tables` (parent/written_by/labels), `search_measure_alias`, `search_fork_class` (UPSERT), `search_fork_label` (чтение), `search_meta.balance_registers`, `search_balance_map`, `search_refcols` (через `refcols_of`), `search_entity_alias` (not_enough_for вне темы, рядом с путём).
- **SQL-функции:** `ts_lexize(STEM_DICT,…)`, `map_keys`/`map_entries`/`map_extract_value` по `nums`/`refs_map`.
- **Env:** `ASK_ENTITY_FORM`, `ASK_FORK_DETECT`, `ASK_FORK_OUTCOMES`, `ASK_FORK_MEAS_TTL`, `ASK_SALES_RANK_CANON`, `ASK_ROWS_TO_MODEL`, `ASK_ATOM_TERMINAL`, `ASK_TOTAL_TEXT`, `ASK_CHOICE_MEMORY`, `ASK_MEMORY_APPLY`, `ASK_DECISION_TTL_SEC`, `ASK_RAW_FOCUS_TRUST`, `ASK_STEM_DICT`, `ASK_NO_DATA_TEXT`, `SERENEDB_DSN_RO` (через `psql`).
- **LLM/HTTP:** `ds_chat` в `rank_axis_pick` (`4941–4955`); `rerank` осей (`4924`); косвенно `refuse_text`→модель при пустом `ASK_NO_DATA_TEXT` (`6046`). В fork/sales/entity-form/исходах/measure_choice — нет.
- **Процессная память:** `_DECISIONS`, `_CLARIFY_BATCHES`, `_RESOLVED_CHOICES` (не диск); shadow через `ACM.attach_choice_memory` при `ASK_CHOICE_MEMORY`.

## Расхождения между отчётами уровня 1

- **расхождение:** отчёт 09 пишет, что `ASK_FORK_DETECT` / `ASK_FORK_OUTCOMES` в участке детектора «объявлены; использование в участке: нет» — верно для диапазона `3935–4760`; в оркестрации оба читаются вместе: ранний скан только при `FORK_DETECT` (`12571`), исходы A/B/C при `FORK_OUTCOMES and FORK_DETECT` (`13356`). Источник: `ubuntu/serenedb/serene_ask.py:12571`, `:13356`.
- **расхождение:** отчёт 09 — флаги memory «объявлены; применение здесь: нет»; отчёт 14 — билеты/shadow без чтения env `ASK_CHOICE_MEMORY` в своём диапазоне. Верно оба: чтение env — `:3957–3959`; `attach_memory_shadow` передаёт `enabled=ASK_CHOICE_MEMORY` (`7219`); применение ветки памяти — `_try_memory_apply` (`15386–15387`). Не конфликт фактов, а разные границы участков.

## Белые пятна

- Как именно считается **число остатка** (SUM по баланс-регистру) — в сырье 05/09–14 нет: участок 12 только отбор/no_data/clarify.
- Тело **`ACM.attach_choice_memory` / постоянная таблица выбора** (если есть) и полный путь `_try_memory_apply` — вне 14; в 14 только вызов shadow и процессные dict.
- Полный круг **арбитра готовых ответов** после empty/unique (`13476+`) и сборка `arb_pool`/writer_pair — за пределами семи отчётов; здесь только стык «после исходов».
- Кто заполняет **`search_fork_label`** (детектор только читает) — по коду этих участков не видно.
- Содержимое **`format_clarify_options` / `clarify_say`** (текст пунктов) — зов есть, реализация вне 14/13.
