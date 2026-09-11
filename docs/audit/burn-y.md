# BURN-Y: приёмка и охрана дожига word-детектора склада (К9-ф3)

Дата: 11.09.2026. Роль Y. Только чтение / проектирование.  
Контракт: маршрутизация склада = `_stock_intent_signal` / `balance_routing_core` (intent) + ось места из метаданных (`search_refcols`); word-механика изъята. OPT-S early-exit — паллиатив, не цель.

---

## 1. Замки, которые уже держат складской путь

Запуск офлайн: `cd /srv/1c/ubuntu/serenedb && python3 <test>.py` (не pytest-пачка).

| Замок | Что проверяет для склада | Связь с word-слоем | После burn |
|---|---|---|---|
| **`test_stock_balance_path.py`** | Главный контур: `balance_path_engaged` / sales-block; named via measure/terms; count-aggregate без subject-clarify; **live intent** без `action_axis` (ось «склад» из текста Q); негатив contractors/org/price → `stock_question_engaged=False`; capable/noise/wiki-path/journal-ghost | **5 кейсов live** зовут `resolved_warehouse_axis_word` / `question_mentions_warehouse_axis` по словам Q (`:102–111`); journal-ghost (`:543+`) — word→catalog | **Переписать live** на intent с `action_axis`/`state`/`object` (без word-резолва). journal-ghost — **вне** маршрутного burn (отдельный пакет, роль Z) или перевести на metadata-only |
| **`test_warehouse_aggregate_breakdown.py`** | K9-ф3 structural: `balance_path_engaged`, skip warehouse-clarify, per-axis breakdown, canon import, breakdown fallback | Уже intent+мок metadata, без маркеров «всего» | Оставить; добавить кейс «sales_sum+list → engaged False» |
| **`test_warehouse_axis_autonomy.py`** | Нет хардкода МестоХранения/масок; ось через `entity_form`+`search_refcols`+`map_extract_value`; clarify 3/1 склад; **include_examples=False** для оси места | Grep по исходникам z12/z05; мок `warehouse_axis_values` | Оставить; усилить: резолв оси **только** из `intent.action_axis` (+ refcols), не из токенов Q |
| **`test_no_domain_wordlists.py`** + **`test_no_domain_baseline.json`** | Трещотка п.0: нет новых DOMAIN_LITERAL / any-in-q / for-header | Базлайн: **z11×23**, **z10×13** (слова склад/остат/всего/товар/продаж); **z12 в базлайне пуст** (литералов маршрута нет — word-loop идёт через словарь базы, не через tuple-маркеры) | После изъятия: `--update-baseline` **только если** счётчики упали; рост = FAIL. O6-выжигание z11/z10 — **не** этот пакет (скоуп: только складская маршрутизация) |
| **`test_fork_outcomes.py`** | `_stock_intent` object+ось → place-класс | Intent-фикстура, не слова | Оставить |
| **`test_wiki_card_hybrid.py`** / **`test_wiki_candidate_verify.py`** | Wiki-каскад при `stock_question_engaged` True/False; мок `resolved_warehouse_axis_word` | Зависит от сигнатуры engaged / axis resolver | Прогнать после смены API; при удалении word-резолва — моки на `action_axis` |
| **`test_rank_axis_anchor.py`**, **`test_k4_axis_and_names.py`**, **`test_k4_guess_vs_clarify.py`** | `question_asks_stock_balance("…на складе?")` — алиас `balance_path_engaged` | Строки Q со «склад» **не** дают True сами по себе (нужен intent); кейсы часто передают только Q | Проверить: без stock-intent → False; поправить фикстуры intent, не возвращать word-гейт |
| **`test_client_gold.py`** / **`test_gold_sets_split.py`** | Формат L67-набора, ∩ рабочих = 0 | Не логика маршрута | Оставить |

Не держит маршрут сам по себе, но входит в приёмочный контур OPT/MOL: `test_step4_guards`, `test_intent`, `test_zone_names_resolvable` — регресс «чужой» зоны после правок z12/z11/z20.

---

## 2. L67: как доказать, что складские вопросы живы

**L67** = приёмочный набор `ubuntu/serenedb/client-gold-okna.tsv` (**67** вопросов; И2 `work/gold/i2_runner.py`).  
Критерий владельца: **уверенно неверных = 0** + доля `honest_no` (не «сколько верных»).

### 2.1 Эталоны про остатки / склад (выписать)

**A. Остатки / разрез по складам — 18 шт.** Эталон сейчас **`no_data`** (честный отказ при живой сверке vitrine). После burn путь обязан остаться **honest_no**, не **confident_wrong** и не «продажи/чужой регистр».

| # строки TSV | Вопрос | etalon |
|---:|---|---|
| 6 | какие позиции имеют нулевой остаток на складе? | no_data |
| 7 | количество уникальных позиций номенклатуры на остатках по складам с разбивкой по складам | no_data |
| 9 | остатки номенклатуры по всем складам, количество позиций на каждый склад отдельно | no_data |
| 10 | остатки по каждому складу отдельно | no_data |
| 11 | остатки по складам: сколько позиций номенклатуры на каждом складе | no_data |
| 12 | остатки товаров по складам: сколько позиций на каждом складе? | no_data |
| 13 | по каким складам числятся остатки товаров и сколько позиций на каждом складе? | no_data |
| 15 | позиции номенклатуры с нулевым остатком | no_data |
| 16 | покажи остатки по каждому складу | no_data |
| 17 | Покажите остатки по всем трём складам сразу | no_data |
| 18 | Покажите остатки по каждому складу отдельно | no_data |
| 19 | Покажите позиции с нулевым остатком | no_data |
| 20 | Покажите список складов с количеством позиций по каждому | no_data |
| 25 | сколько всего позиций номенклатуры числится на всех складах компании? | no_data |
| 60 | сколько на складе позиций всего? | no_data |
| 62 | сколько позиций на всех складах вместе? | no_data |
| 63 | сколько позиций на каждом складе отдельно? | no_data |
| 68 | сколько у нас петель осталось на складе | no_data |

**B. Список складов как справочник (не stock-balance path) — 3 шт.** Эталон **`3`** (match). Burn **не** должен увести их в stock-фильтры; это `catalog_*` / wiki-list.

| # | Вопрос | etalon |
|---:|---|---|
| 5 | какие есть склады | 3 |
| 8 | Места Хранения: перечислить склады | 3 |
| 26 | сколько всего складов и какие у них названия | 3 |

**C. Негатив sales (контроль ложного engage) — минимум из L67:**

| # | Вопрос | etalon |
|---:|---|---|
| 4 | вчера сколько продали | 645641.67 |
| 14 | позавчера сколько было продаж | 0.00 |
| 35/36/53 | движения/записи «книгапродаж» | числа |

Плюс **вне L67**, обязательный rid-класс из OPT: «продажи + полный отчет» — `stock_question_engaged=False`, wall Z4→Z6 без stock-фильтров (зонд был 50,6 с).

### 2.2 Протокол L67-stock (полигон → бой)

```bash
# 1) офлайн-замки (см. §1 + §3)
cd /srv/1c/ubuntu/serenedb
for t in test_no_domain_wordlists test_stock_balance_path \
  test_warehouse_aggregate_breakdown test_warehouse_axis_autonomy \
  test_fork_outcomes test_burn_stock_word_absent; do
  python3 "$t.py" || exit 1
done

# 2) L67-stock slice (engine-path достаточно до web)
python3 work/gold/i2_runner.py run \
  --tsv ubuntu/serenedb/client-gold-okna.tsv \
  --path engine \
  --only-grep 'остат|склад|петель|Места Хранения|какие есть склады|всего складов' \
  --out work/gold/runs/burn-l67-stock

# 3) L67-sales контроль (не ≡ старому stock-искажённому)
python3 work/gold/i2_runner.py run \
  --tsv ubuntu/serenedb/client-gold-okna.tsv \
  --path engine \
  --only-grep 'продали|продаж|книгапродаж' \
  --out work/gold/runs/burn-l67-sales
```

Если `--only-grep` в раннере нет — отфильтровать TSV-срез вручную (21 строка A+B / 5 строк C) тем же `i2_runner`.

**Вердикт pass:**

| Класс | Pass |
|---|---|
| A (18) | `confident_wrong=0`; `honest_no` или `match` не хуже baseline; **diag**: stock engage согласован с intent (True при object/state+ось, не от слова «склад» в Q) |
| B (3) | `match` к `3`; **не** `stock_non_goods_drop` / тяжёлые stock-фильтры |
| C + rid | числа/канон продаж; `stock_question_engaged=False`; субмаркер detect ≤ N мс (§4) |

Полный L67 (все 67) — перед выкатом на прод; полигон сначала на A+B+C.

---

## 3. Замки обновить / добавить (трещотка)

### 3.1 Новый: `test_burn_stock_word_absent.py` (обязателен в том же коммите, что изъятие)

Grep/AST-замок по маршруту склада — **не** полагаться только на `no_domain` (z12 может не иметь tuple-литералов).

| Проверка | Ожидание |
|---|---|
| В `ask/z12_stock_balance.py` **нет** вызовов/`def` маршрутных: `question_has_aggregate_total_marker`, word-ветка `resolved_warehouse_axis_word` по токенам Q (`_question_dictionary_axis_candidates` в `stock_question_engaged` / `question_mentions_warehouse_axis`), word-loop входа в `catalog_kind_total_question` через warehouse-mention | функции либо удалены, либо сужены до intent-only |
| В `stock_question_engaged` / `balance_path_engaged` цепочка только: `sales_sum`/`catalog_*` гейты → `_stock_intent_signal` / `balance_routing_core` → `_kind_is_stock_scoped` / `action_axis`↔`search_refcols` | нет `for w in re.finditer` / `_question_dictionary_axis_candidates` на решении True/False |
| В `z11_sales.catalog_kind_total_question` нет обязательного зонда `question_mentions_warehouse_axis` до kind→catalog | short-circuit по intent; warehouse — metadata |
| В `z20` точки `:2187`, `:2232`, `:2270`, `:2672`, `:4399` зовут **один** кэшированный pred (OPT-C остаётся) | без повторного word-SQL |
| Запрет новых DOMAIN_LITERAL / any-in-q со «склад/остат/всего» в z12/z20 маршруте | стык с `test_no_domain_wordlists` |

Имена-заглушки после удаления: если алиасы оставлены для совместимости тестов — тело = intent-only, **без** чтения токенов Q.

### 3.2 Обновить существующие

| Файл | Правка |
|---|---|
| `test_stock_balance_path.py` | Блок «live intent: dict axis from question» → **intent-фикстура** с `action_axis="склад"` (или state_path + axes) и пустым/нейтральным Q `"q"`; убрать зависимость True от токена «складе» |
| `test_warehouse_aggregate_breakdown.py` | +негатив: `sales_sum` + `want=list` → `stock_question_engaged is False` без тяжёлого psql |
| `test_warehouse_axis_autonomy.py` | +ассерция: при пустом `action_axis` и Q со словом «склад» **без** metadata-confirm → axis/engaged не True «по слову» |
| `test_no_domain_baseline.json` | После реального выжигания z11/z10 (O6) — `--update-baseline` отдельным коммитом; **в burn-пакете** не трогать sales-легаси |
| `test_rank_axis_anchor` / k4 | Фикстуры intent для stock-True; Q-only без intent → False |

### 3.3 Не смешивать в этом пакете

- O6 полное выжигание z11×23 / z10×13 («всего» в продажных путях) — **скоуп Role Z**: burn трогает только складскую маршрутизацию.
- journal-ghost / инертные stock-helpers — отдельное решение.
- OPT-S early-exit как единственная правка — **отклонён** владельцем; кэш OPT-C — второй слой, остаётся.

---

## 4. Субмаркеры: «stock-детект ≤ N мс»

Сейчас `шаг()` пишет **накопленное** время от `t0` (`z20:1844–1846`), не длительность участка. Для burn нужны **дельты участка** (как C0 в opt-c), иначе N мс не доказать.

### 4.1 Форма (TRACE, без смены логики маршрута)

В `z20_ask_main_http.py` вокруг stock#1 (`:2232`) и stock#2 (`:2270`):

```text
шаг("stock#1 detect enter")
engaged = stock_question_engaged(...)   # кэш diag, OPT-C
шаг("stock#1 detect done", engaged=bool(engaged),
    detect_мс=<wall_ms этой строки>, route="intent"|"cache")
# … filters only if engaged …
шаг("stock#1 filters done", …)

шаг("stock#2 detect enter")
…
шаг("stock#2 detect done", engaged=…, detect_мс=…, cache_hit=0|1)
шаг("stock#2 filters done", …)   # или skip_filters=1
```

Допустимо писать `detect_мс` в `diag` отдельно (`diag["stock_detect_ms"]`), а в `шаги` — краткий маркер; главное — **локальная** длительность, не `мс` от старта ответа.

Опционально внутри z12 (один раз на запрос):  
`diag["stock_detect_parts"] = {intent_ms, meta_ms, word_ms}` — после burn `word_ms` обязан быть **0** или ключ отсутствует.

### 4.2 Бюджет N

| Ситуация | N (полигон, тёплый meta-кэш place-axis) | Доказательство |
|---|---|---|
| **Негатив sales / «полный отчет»** | **`detect_мс ≤ 5`** (цель); soft-fail до **50** на холодном первом meta | engaged=False; filters не бегут; Z4→Z6 без 50 с |
| **Позитив stock (intent уже object/state + axis)** | **`detect_мс ≤ 50`** без EXISTS корпуса; SQL только refcols/place-кэш | engaged=True; дальше filters отдельно субмаркерами |
| **Повтор #2 / внутренние зовы** | **`detect_мс ≤ 1`**, `cache_hit=1` | OPT-C |

Не смешивать detect с `registers_for_kind_axes`/EXISTS (это filters, десятки секунд на ложном engage) — иначе снова спутаем с OPT-S зондом 50,6 с.

### 4.3 Замер приёмки (3 класса + detect)

| Класс | Q | Wall (W4) | Обязательные маркеры |
|---|---|---|---|
| Простой остаток | из A (напр. стр.60 / 68) | ≤15 с | `stock#1 detect done` engaged=1, detect_мс≤50; нет ложного sales-canon |
| Меню / list складов | B стр.5/8/26 | ≤20 с | engaged склада-balance **0** или catalog-path; detect_мс≤5 |
| Полный отчёт / продажи | rid + L67 C | ≤40 с (цель); detect≪ | engaged=0, detect_мс≤5; Z7→собраны без второго filters-прохода |

Снимать на полигоне `:8092` (или эквивалент) **после** изъятия word + кэша C; memo/INTENT помечать холод/тёплый.

---

## 5. Чеклист приёмки burn (сводка для оркестратора)

1. Офлайн: stock + warehouse + **новый grep-замок** + no_domain (счётчик не вырос).  
2. Переписаны live/word-зависимые кейсы в `test_stock_balance_path`.  
3. TRACE-субмаркеры detect_мс влиты (можно отдельным коммитом до/с кодом).  
4. L67-stock A+B: wrong=0; L67-sales C + rid: engaged=0, detect≤N.  
5. Wiki-замки зелёные.  
6. OPT-C кэш остаётся; OPT-S-only early-exit **не** считать закрытием К9-ф3.

---

*Конец BURN-Y. Код не менялся.*
