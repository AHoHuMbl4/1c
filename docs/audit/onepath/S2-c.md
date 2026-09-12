# S2-c: три silent-выбирателя → меню / единственный (проект)

Срез: 12.09.2026. Read-only по коду `ubuntu/serenedb/ask/` (прод-тракт «один путь»).
Код не менялся. Чужие S2-отчёты не читались; опора — живой код + реестр W2 (A1/A2/A3, R2/R3).

**Контракт (владелец):** ровно один живой кандидат → взять; >1 неразличимых/одноимённых → `readings_menu` (подписи из данных/вики, различители вроде «документ / регистр накопления»). Меню — только построителем (`readings_menu` → `clarify_opts_response`). Новых выбирателей не заводить.

**Горячий тракт:** `answer` в `z20_ask_main_http.py` — вики → меню окна/меры/оси **до** SQL → SQL → compose+gate.

---

## Сводка

| Символ | Живёт | Зов из нового тракта | Silent при >1 | Класс L67 |
|---|---|---|---|---|
| `measure_choice` | `z14_clarify_memory.py:30` | `_settle_measure` ← `answer` (~2026); вложенно `_stock_qty_measure_name` ← `stock_net_register_pair` | ветки `base` (+ принятие любого `_got` в settle); fallback `names[0]` в stock-qty | **sum/rank** (мера); косвенно **stock** |
| `_pick_kind_axis_col` | `z05_entity_form.py:663` | `live_axis_col_for_count` ← `answer` SQL (~2178); также boolean в `count_defer_measure_clarify` (~2018) | `kind_axis_rerank(…)[0]` / `matched[0]` / `hits[0]` | **count** (DISTINCT vs строки) |
| `stock_net_register_pair` | `z12_stock_balance.py:962` | `aggregate_stock_net_distinct` ← `answer` SQL (~2168) | среди siblings≥2 код назначает receipt/expense (+ qty/axis) | **stock** (net-distinct) |

Общий дефект: выбор делается **после** (или в обход) ступени меню, молча при нескольких кандидатах.

---

## 1. `measure_choice`

### 1.1 Где живёт / кто зовёт из нового тракта

- **Определение:** `ubuntu/serenedb/ask/z14_clarify_memory.py:30–83`.
- **Горячий путь меры:**
  1. `z20_ask_main_http.py:1501` — `_settle_measure`
  2. внутри: `:1534` и `:1539` — `measure_choice(names, word, alias_by=alias)`
  3. `answer` (~`:2026`) зовёт `_settle_measure`; при `len(measure_alts)>1` — уже легитимное меню через `_measure_menu_opts` + `readings_menu(..., "measure", ...)` (~`:2028–2035`).
- **Вложенный горячий путь (stock):**
  - `z12_stock_balance.py:941` `_stock_qty_measure_name` → `measure_choice(..., "колич")` (`:956`)
  - зовётся из `stock_net_register_pair` (`:1008`) → `aggregate_stock_net_distinct` → `answer` `:2168`.
- **Не новый тракт (не цель правки, но живые потребители):** `z11_sales.py:309` (`sales_money_measure`), `z12:671` / `:1197` (`rank_measure_hint` / `_breakdown_fallback_measure`), offline `entity_rank_v2._measure_choice`. В `z20` прямых вызовов `sales_money_measure` / `rank_measure_hint` нет.

### 1.2 Когда выбирает молча при >1 имени в `names`

Контрактное «один кандидат» здесь = **один после фильтра по слову**. Нарушение — когда после фильтра остаётся >1, а код всё равно отдаёт победителя.

| `how` | Условие ветки | Silent при >1? |
|---|---|---|
| `single` | `len(names)==1` | нет (единственный) |
| `exact` | `n.lower()==wl` → `exact[0]` | нет по фильтру (ровно одно точное имя; при дублях регистре — краевой silent) |
| `alias` | ровно один `covered` по алиасам | нет (один после фильтра) |
| **`base` (alias)** | `len(covered)>1` и один префикс-«базовый» → вернуть его | **да** (`:60–65`) |
| `ask` (alias) | `len(covered)>1` без единственного base | нет → меню |
| **`base` (substring)** | `len(same)>1` и один base-префикс | **да** (`:68–74`) |
| `ask` (substring) | `len(same)>1` без base | нет → меню (alts = same + остальные) |
| `substring` | `len(same)==1` | нет |
| `rerank` / `none` | нет совпадений | не выбирает |

**Усилитель в settle:** `_settle_measure` при любом `_got` сразу `return _got, []` (`:1540–1541`) — silent-ветки `base`/`exact`/`alias`/`substring` **никогда не доходят** до `readings_menu`, даже если в `names` много равноправных денежных полей.

**Усилитель в stock-qty:** если `measure_choice` не дал `got` с «хорошим» how — `return names[0]` (`z12:959`). Это silent first при любом `len(names)>1`.

### 1.3 Проект перевода на контракт

1. **Сузить `measure_choice` до детектора кандидатов**, без победителя при >1:
   - оставить `single` / единственный `exact` / единственный `alias` / единственный `substring`;
   - ветки **`base` убрать или перевести в `ask`**: при `len(covered|same)>1` всегда `(None, candidates, 'ask')` — даже если есть префикс-база;
   - не вводить новый выбиратель; не звать rerank из меры.
2. **`_settle_measure`** оставить единственной точкой решения на тракте:
   - 0 кандидатов → дальше по существующим веткам (`_need` → меню всех `names` / none);
   - 1 → взять;
   - >1 → `return None, list(alts)` → уже есть путь `readings_menu` + `_measure_menu_opts`.
3. **Опции / подписи (уже есть):** `_measure_menu_opts` (`z20:1485`) — `measure_captions` + `entity_label` из `TABLES.label`; билет ambiguity=`measure` (ключ `"measure"` в option).
4. **`_stock_qty_measure_name`:** убрать `names[0]`; при >1 qty-кандидатах — не собирать пару молча, а поднять меню меры **до SQL** (тот же `readings_menu`/`measure`), либо вернуть «нет единственной qty» и не входить в net-distinct.
5. Замки: расширить `test_measure_menu_not_silent` / gate-кейсы на запрет `how=='base'` при `len(covered)>1`; чёрный список one_path — не имя `measure_choice` (детектор нужен), а запрет silent-потребления `_got` без проверки `len(alts)`.

### 1.4 Риски L67

- **sum / money-вопросы:** эталоны, где сейчас «угадывается» `Сумма` как base среди `Сумма*` / НУ/ВР — станут clarify. Match→clarify не wrong, но динамика match упадёт, пока человек/билет не выберет; после билета — стабильнее.
- **rank:** на горячем пути мера идёт через `_settle_measure`; смена `base`→меню затронет rank с словом меры / без явного билета. `rank_measure_hint` вне z20 — не трогать в этом эпизоде, иначе расползание.
- **stock:** через `_stock_qty_measure_name` — см. §3; неверный `Количество*` молча даёт другой net.

---

## 2. `_pick_kind_axis_col` (z05:663+)

### 2.1 Где живёт / кто зовёт из нового тракта

- **Определение:** `ubuntu/serenedb/ask/z05_entity_form.py:663–695`.
- **Обёртка:** `live_axis_col_for_count` (`:698–737`) → единственный return через `_pick_kind_axis_col` (`:734`).
- **Горячий SQL-путь:** `z20_ask_main_http.py:2174–2184`:
  - если `grain_dec.col` уже есть и `want in (count,"")` — берёт его;
  - иначе `live_axis_col_for_count(intent, src, axes, named_entity=…)` → при успехе `aggregate_distinct_axis`.
- **До SQL (гейт, не меню):** `count_defer_measure_clarify` ← `answer` `:2018–2022` — truthiness `live_axis_col_for_count` пропускает меню меры на count (это OK как класс вопроса), но при этом **уже** мог бы отреранжировать ось внутри вызова.
- **Побочные (не return ответа, но silent-логика та же):** `event_count_has_live_axis`, `event_duel_applies`, `_event_distinct_fork_rows` в z05 — после S2-сноса fork-терминалов на тракте не доминируют; править тем же контрактом детектора.

`kind_axis_rerank` в **z20 запрещён** замком B4 (`test_one_path`: `0 kind_axis_rerank`), но жив в z05 и зовётся из `_pick_kind_axis_col` — обход чёрного списка файла z20.

### 2.2 Когда выбирает молча при >1

После фильтра `matched` (target_src ∈ kind_cats) или `hits` (`kind_axis_hits`):

| Ветка | Условие | Действие |
|---|---|---|
| sole matched | `len(matched)==1` | `matched[0]["col"]` — **OK** |
| **multi matched** | `len(matched)>1` | `kind_axis_rerank(matched)[0]` иначе **`matched[0]["col"]`** — **silent** (`:684–687`) |
| sole hit | `len(hits)==1` | OK |
| **multi hits** | `len(hits)>1` | `reranked[0] if reranked else hits[0]` — **silent** (`:693–695`) |

Итог: при любом ≥2 кандидатах всегда одна колонка, меню не строится. Вызов стоит **после** ступени axis-меню (`_settle_axis`), часто когда count-вопрос **намеренно** скипнул axis clarify (`count_question_skips_axis` / `count_defer`).

### 2.3 Проект перевода на контракт

1. **Разделить детект и выбор:**
   - `_kind_axis_col_candidates(ax, axis_word, intent, …) → list[col]` (или list axis-dict) — без rerank-победителя;
   - `_pick_kind_axis_col` либо удалить с горячего пути, либо оставить тонкой обёрткой: `len==1 → col; len>1 → None` (без `[0]`).
2. **Поднятие меню до SQL** в `answer` (рядом с существующим axis-меню, ~`:2043–2053`):
   - для count/DISTINCT, когда нужен live-axis и кандидатов >1 → `axis_clarify_options` **по подмножеству** кандидатов (не всем refcols) → `readings_menu(..., "axis", …)`;
   - подписи уже из `TABLES.label` target_src (`z18:27–51`); при одноимённых labels — добавить различитель колонки/`split_ident(col)` (как `measure_captions` для дублей).
3. **После билета:** `grain_dec.col` / trusted axis уже умеют закрывать путь (`grain_dec_from_axis_ticket`); SQL тогда не зовёт silent pick.
4. **`count_defer_measure_clarify`:** опираться на `bool(candidates)`, не на выбранную колонку — иначе defer зависит от rerank.
5. **Не** возвращать `kind_axis_rerank` в z20; не плодить второй построитель clarify.

### 2.4 Риски L67

- **count:** главный класс. Исторический баг (комментарий z05:704–708, z17:431–433): «движений в регистре …» → DISTINCT по случайному роду («Виды деятельности») вместо числа строк. Меню при >1 **улучшает** честность; эталоны, где silent rerank случайно совпал с эталоном, станут clarify или потребуют билет.
- **rank:** `_settle_axis` уже имеет свой путь `rank_axis_resolve` (≥2 → hatch/alts); `_pick_kind_axis_col` на rank-GROUP BY не главный. Риск низкий, если не смешивать правки.
- **stock:** низкий прямо; косвенно если stock-count идёт через distinct-axis.

---

## 3. `stock_net_register_pair`

### 3.1 Где живёт / кто зовёт из нового тракта

- **Определение:** `ubuntu/serenedb/ask/z12_stock_balance.py:962–1011`.
- **Потребитель:** `aggregate_stock_net_distinct` (`:1014`) → `pair = stock_net_register_pair(...)` (`:1020`).
- **Горячий путь:** `z20_ask_main_http.py:2164–2173` — только если ещё нет `agg`, сработал `stock_count_aggregate_without_subject`, и есть `measure` / `_count_defer` / `grain_dec.col`.
- Вспомогательные silent внутри пары:
  - `_sort_stock_pool` / `_stock_register_rank_key` (`:898–921`);
  - `stock_balance_is_sales_noise` / `reversal_noise` (фильтр + роль);
  - `_stock_product_axis_col` — **первый** product-catalog refcol (`:924–938`);
  - `_stock_qty_measure_name` — см. §1.

### 3.2 Когда выбирает молча при >1

Условие входа в выбор: `by_pt` группа с `len(siblings)≥2`, после noise `len(active)≥2`.

Дальше код **всегда** назначает пару без меню:

1. `sorted_s = _sort_stock_pool(active)` — ранжирование;
2. `receipt` = первый «не sales-noise», иначе `sorted_s[0]`;
3. `expense` = первый sales-noise, иначе `max(others, key=corpus_count)`;
4. берёт первую удачную `(receipt, expense, prod_col, qty)` по product-target и **return** — следующие группы `by_pt` не предлагаются человеку.

Это silent при любом ≥2 регистрах на одной товарной оси (и при неоднозначной роли приход/расход).

### 3.3 Проект перевода на контракт

1. **Детектор вместо пары-победителя**, например `stock_net_register_candidates(...) → list[{receipt, expense, prod_col, qty_cands, labels}]` или плоский список регистров-прочтений:
   - 0 → как сейчас `None` (нет net-ветки);
   - 1 валидная пара / один способ сборки → взять;
   - >1 → меню **до SQL**.
2. **Опции / подписи** (через существующий `readings_menu`, без нового clarify-API):
   - предпочтительно **меню регистров-ролей** (ambiguity=`entity` по `ambiguity_of_options`, если нет `measure`/`period`/`distinct_by`):  
     `{ "src": reg, "label": "<wiki label> (регистр накопления, приход|расход)", "entity_label": wiki_label }`  
     подписи — из вики/`TABLES.label` (тот же дух, что меню одноимённых document vs accumulationregister);
   - либо меню **пар**: одна option = два src в payload (нужна аккуратность билета `issue_decision` — сейчас ticket хранит один `src`; проще два шага меню или option с `src`=receipt и полем-спутником, читаемым при consume — **не** новый выбиратель, но потребуется узкое расширение билета; зафиксировать в реализации отдельно).
3. **Вложенные qty/axis:** те же правила §1–§2 — sole → take; >1 → `readings_menu` measure/axis до сборки SQL net.
4. Фильтры noise (`sales_noise` / `reversal`) оставить как **отсев не-кандидатов** (легитимный классификатор), не как выбор среди оставшихся равноправных.
5. Точка в `answer`: перед блоком `:2164`, в секции меню (~шаг 6), если `stock_count_aggregate_without_subject` и кандидатов пары >1 — `return readings_menu(...)`; SQL только после sole/билета.

### 3.4 Риски L67

- **stock:** прямой класс. Net COUNT(DISTINCT product) зависит от выбранной пары регистров и qty-поля; silent сейчас стабилизирует «счастливый» эталон на okna и ломается на другой базе (нарушение автономии).
- **count:** пересечение — складские count без subject идут в net-distinct; эталоны count-на-складе могут уйти в clarify.
- **rank:** почти не затронут.

---

## 4. Порядок внедрения (рекомендация)

1. **`measure_choice` / `_settle_measure`** — локально, замки menu-not-silent + gate; L67 sum/rank смотреть первыми.
2. **`_pick_kind_axis_col` → candidates + axis-меню до SQL** — L67 count; не возвращать rerank в z20.
3. **`stock_net_register_pair` → candidates + меню регистров/пар до SQL** — L67 stock; заодно убрать `names[0]` в qty.
4. Полный `test_one_path` (а–г): clarify только построителем; нет вторых чисел; SQL после wiki; чёрные списки. Дополнить чёрный список **потребления** silent (например запрет `kind_axis_rerank` не только в z20, а assert что live-axis path не зовёт winner при `len>1` — отдельным замком зоны z05/z12, не новым выбирателем).
5. Контрольный L67 на проде/полигоне → выкат.

---

## 5. Вне скоупа этого проекта (не молчать, не лечить здесь)

- Одноимённые **wiki-прочтения** document vs register («реализациятмц») — отдельное правило меню в z21 (контекст задачи владельца); не подменять verify-лотерею этими тремя символами.
- `rank_axis_resolve`, `sales_money_measure`, period-repair — другие silent из W2; не смешивать в один дифф с S2-c.
- Мёртвые символы смешанных зон (~2.2k) — волна S2-чистки символов, не этот отчёт.

---

## 6. Критерий готовности эпизода

- При `len(candidates)==1` поведение как сейчас (sole).
- При `len(candidates)>1` на горячем пути: **только** `readings_menu` / `clarify_opts_response`; ни `base`, ни `rerank[0]`, ни `matched[0]`, ни `max(corpus)`, ни `names[0]`.
- `test_one_path` зелёный полностью; точечные замки measure/axis/stock; L67 без роста wrong на count/stock/rank из-за нового silent (рост clarify допустим и ожидаем).
