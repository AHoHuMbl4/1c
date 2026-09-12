# W1 — карта живости `ask/z10_rank.py`

Дата: 12.09.2026. Только чтение кода. Метод: AST верхнего уровня зоны +
grep/AST по `ask/*.py` (общий namespace, без доверия import-структуре);
new/legacy z20 считаются **взаимоисключающими** корнями (`ASK_ONEPATH` /
`_bootstrap._Z20_FILE`) — одноимённые `gate`/`answer` между ними в граф
не склеивались.

Файл зоны: `ubuntu/serenedb/ask/z10_rank.py` (471 строка файла;
сумма тел символов верхнего уровня = **422**).

---

## Итог зоны

| Вердикт | Символов | Строк (тел) |
|---|---:|---:|
| **ЖИВА НОВОМУ** (прямо или транзитивно) | 10 | **246** |
| **ЖИВА ТОЛЬКО LEGACY** | 0 | **0** |
| **МЁРТВА** (нет зовов из трактов; только тесты / никого) | 7 | **176** |
| Всего символов | 17 | 422 |

**Вердикт по зоне:** зона **нужна одному пути**. Ядро ранга
(`rank_intent_from` → `rank_axis_resolve` и skip-axis гейты) прямо сидит в
`_settle_axis` нового z20. После сноса legacy объём зоны не ужимается по
живости тракта (legacy-only символов нет); мёртвые 176 строк — отдельный
хвост (leader-текст/atom, period-clarify, theme-pick, compat-обёртка).

---

## Таблица символов

| Символ | Строки | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `count_question_skips_axis` | 24 | **new** `z20_ask_main_http.py:1575` (`_settle_axis`); **legacy** `z20_ask_main_http_legacy.py:3635` (`answer`); внутри: —; тесты: `test_axis_count_plain.py`, `test_b9_routing.py` | **ЖИВА НОВОМУ** |
| `question_wants_breakdown` | 13 | **new** `:1590` (`_settle_axis`); **legacy** `:3590`; зоны: `z12_stock_balance.py:316,362,366,378,413` (`aggregate_count_intent` / `balance_routing_core` / `_stock_intent_signal` / `question_wants_per_axis_breakdown` — все достижимы из new `answer`); внутри: `count_question_skips_axis:23`, `total_question_skips_axis:57`; тесты: `test_axis_count_plain.py`, `test_rank_axis_anchor.py`, `test_terminal_round.py` | **ЖИВА НОВОМУ** |
| `total_question_skips_axis` | 19 | **new** `:1579`; **legacy** `:3648`; тесты: `test_axis_count_plain.py`, `test_rank_axis_anchor.py`, `test_terminal_round.py` | **ЖИВА НОВОМУ** |
| `rank_question_text` | 19 | зон: `z02_intent.py:386` и `z16_veto_pick_entity.py:350` (`question_expects_accounting_data` ← wiki-каскад new); `z05_entity_form.py:28,160` (`entity_form_rank_single_window` / `sales_compare_intent` ← new `answer`); **только legacy:** `z11_sales.py:165` (`sales_rank_engaged`); внутри: `rank_intent_from:105`; тесты: `test_rank_axis_anchor.py` | **ЖИВА НОВОМУ** |
| `rank_intent_from` | 14 | **new** `:1591,:1594` (`_settle_axis`), `:1639` (`_onepath_compose_gate`); **legacy** `:3312,:3591,:3604,:3974,:4073`; зоны (new): `z05:190,751`, `z12:314,361,638`, `z21_wiki_choice.py:67` (`wiki_aggregate_want`); зоны (**только legacy**): `z11:158` (`sales_rank_engaged`), `z12:648` (`_rank_wants_quantity`), `z13:147` (`rank_defer_fork_outcome_b`); зоны (**orphan / мёртвый зовущий**): `z06:560` (`entity_pick_counts_for_model`), `z11:263` (`sales_canon_intent`), `z12:667` (`rank_measure_hint`); внутри: `total_question_skips_axis`, `count_theme_code_pick_applies`, `rank_period_clarify_applies`; тесты: `test_axis_count_plain`, `test_entity_form`, `test_rank_*`, stubs в `test_wiki_*` / `test_named_type_filter` | **ЖИВА НОВОМУ** |
| `rank_leader_answer_text` | 21 | внешних зовов в ask нет; тесты: `test_rank_leader_path.py`, `test_rank_axis_anchor.py`, `test_unit_from_data.py` | **МЁРТВА** |
| `AXIS_PICK_SYS` | 12 | **new** `:755` (`OUR_PROMPTS`); **legacy** `:761`; внутри: `rank_axis_pick:212` | **ЖИВА НОВОМУ** |
| `rank_axis_label_rows` | 24 | только внутри: `rank_axes_rerank:179`, `rank_axis_pick:201` (вход с new через `rank_axis_resolve`) | **ЖИВА НОВОМУ** (транзитивно) |
| `rank_axes_rerank` | 12 | только внутри: `rank_axis_resolve:269,:286`; тесты патчат в `test_rank_leader_path.py` | **ЖИВА НОВОМУ** (транзитивно) |
| `rank_axis_pick` | 47 | только внутри: `rank_axis_resolve:265`; тесты патчат в `test_rank_leader_path.py`, `test_rank_axis_anchor.py` | **ЖИВА НОВОМУ** (транзитивно) |
| `rank_axis_resolve` | 62 | **new** `:1597` (`_settle_axis`); **legacy** `:3609`; тесты: `test_rank_leader_path`, `test_rank_axis_anchor`, `test_measure_menu_not_silent` | **ЖИВА НОВОМУ** |
| `rank_product_axis_col` | 4 | никто (compat-обёртка над `rank_axis_resolve`; внешних/тестовых зовов нет) | **МЁРТВА** |
| `rank_leader_atom` | 32 | внешних зовов в ask нет; тесты: `test_rank_leader_path.py`, `test_unit_from_data.py` | **МЁРТВА** |
| `count_theme_code_pick_applies` | 56 | внешних зовов в ask нет; тесты: `test_entity_form.py:478`, `test_k6_rank_v2.py:86` | **МЁРТВА** |
| `rank_period_unspecified` | 12 | только внутри: `rank_period_clarify_applies:425` (цепочка мёртвая) | **МЁРТВА** |
| `rank_period_clarify_applies` | 24 | только внутри: `try_rank_period_clarify:444`; тесты: `test_rank_leader_path.py:231`, `test_k6_rank_v2.py:90` | **МЁРТВА** |
| `try_rank_period_clarify` | 27 | никто в ask/z20; тестов прямого зова нет | **МЁРТВА** |

### Bootstrap / imports / wire

| Файл | Упоминание z10 |
|---|---|
| `_bootstrap.py:33` | имя файла `"z10_rank.py"` в `_ZONE_FILES` (загрузка зоны) |
| `_imports.py` | символов зоны нет |
| `_wire.py` | символов зоны нет |
| сама зона | `apply_bindings(globals())`; `register_zone('ask.z10_rank', globals())` |

getattr/f-строк с именами символов зоны в ask-тракте не найдено (кроме
diag-ключей вроде `rank_axis_alts` — не зов функции).

---

## Транзитивные цепочки (к корню z20)

Формат: `символ ← … ← answer` (new или legacy). Показаны **короткие**
представители; полный список прямых сайтов — в таблице.

### ЖИВА НОВОМУ — прямые входы

1. `count_question_skips_axis` ← `_settle_axis` ← **new** `answer`
2. `total_question_skips_axis` ← `_settle_axis` ← **new** `answer`
3. `question_wants_breakdown` ← `_settle_axis` ← **new** `answer`
4. `rank_intent_from` ← `_settle_axis` / `_onepath_compose_gate` ← **new** `answer`
5. `rank_axis_resolve` ← `_settle_axis` ← **new** `answer`
6. `AXIS_PICK_SYS` ← **new** `<module>` (`OUR_PROMPTS`)

### ЖИВА НОВОМУ — внутри зоны от `rank_axis_resolve`

7. `rank_axis_pick` ← `rank_axis_resolve` ← `_settle_axis` ← **new** `answer`
8. `rank_axes_rerank` ← `rank_axis_resolve` ← …
9. `rank_axis_label_rows` ← `rank_axis_pick` / `rank_axes_rerank` ← …
10. `AXIS_PICK_SYS` ← `rank_axis_pick` ← … (второй вход, кроме `OUR_PROMPTS`)
11. `rank_question_text` ← `rank_intent_from` ← …

### ЖИВА НОВОМУ — через другие зоны

12. `rank_question_text` ← `sales_compare_intent` ← **new** `answer`
13. `rank_question_text` ← `entity_form_rank_single_window` ← `sales_compare_intent` ← **new** `answer`
14. `rank_question_text` ← `question_expects_accounting_data` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade` ← **new** `answer`  
    (на диске дубль в `z02` и `z16`; в runtime побеждает поздний `z16`)
15. `rank_intent_from` ← `sales_compare_intent` ← **new** `answer`
16. `rank_intent_from` ← `count_defer_measure_clarify` ← **new** `answer`
17. `rank_intent_from` ← `grain_dec_from_axis_ticket` ← `_settle_axis` ← **new** `answer`
18. `rank_intent_from` ← `aggregate_count_intent` ← `stock_count_aggregate_without_subject` ← **new** `answer`
19. `rank_intent_from` ← `balance_routing_core` ← … ← **new** `answer`
20. `rank_intent_from` ← `wiki_aggregate_want` ← `_wiki_hybrid_vars` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade` ← **new** `answer`
21. `question_wants_breakdown` ← `aggregate_count_intent` / `balance_routing_core` / `_stock_intent_signal` / `question_wants_per_axis_breakdown` ← … ← **new** `answer`

### Те же входы с legacy (не exclusive)

Параллельно: `count_*` / `total_*` / `question_wants_breakdown` /
`rank_intent_from` / `rank_axis_resolve` / `AXIS_PICK_SYS` ← **legacy**
`answer` (и модульный `OUR_PROMPTS`). Отдельных legacy-only символов зоны нет.

### Цепочки, живые только legacy (зовущий — не символ z10)

Эти **зовущие** тянут символы z10, но сами из new `answer` недостижимы
(без склеивания с legacy `gate`/`answer`):

- `sales_rank_engaged` ← legacy `answer` → `rank_intent_from`, `rank_question_text`
- `_rank_wants_quantity` ← legacy `answer` → `rank_intent_from`
- `rank_defer_fork_outcome_b` ← legacy `answer` → `rank_intent_from`

Символы при этом всё равно **ЖИВА НОВОМУ** другими путями.

### Orphan-зовущие (ни new, ни legacy)

- `entity_pick_counts_for_model` → `rank_intent_from`
- `sales_canon_intent` → `rank_intent_from`
- `rank_measure_hint` → `rank_intent_from`

### Мёртвые цепочки внутри зоны

- `rank_period_unspecified` ← `rank_period_clarify_applies` ← `try_rank_period_clarify` ← ∅
- `rank_product_axis_col` ← ∅
- `rank_leader_answer_text` / `rank_leader_atom` / `count_theme_code_pick_applies` ← ∅ (ask)

---

## Скрытые выбиратели, доступные НОВОМУ тракту

Через транзитивные/прямые зовы из new `answer` зона **тащит** в один путь:

| Механизм | Что выбирает кодом | Как входит в new |
|---|---|---|
| **`rank_axis_resolve`** (+ `rank_axis_pick` / `rank_axes_rerank` / `rank_axis_label_rows` / `AXIS_PICK_SYS`) | **Ось GROUP BY**: модель по меткам → stem/kind hits → rerank; 1 ось — авто; ≥2 — меню (`None, alts`) | прямо `_settle_axis` при `rank_intent_from` |
| **`rank_intent_from`** / **`rank_question_text`** | Класс «это рейтинг/топ» по `want`/`amount`/`compute`/фразам вопроса (маркеры «больше всего», «топ», …) | `_settle_axis`, `_onepath_compose_gate`, wiki/sales/stock зоны |
| **`count_question_skips_axis`** / **`total_question_skips_axis`** | Снять axis-clarify без вопроса человеку (count/list/«всего»/sum) | `_settle_axis` |

Это **скрытые выбиратели оси/класса вопроса**, не источника и не меры.
Выбора периода из этой зоны в new **нет** (`try_rank_period_clarify` мёртв;
`rank_period_clarify_applies` к тому же в конце всегда `return False`).

**Не** входят в new (мёртвы): `count_theme_code_pick_applies` (выбор
сущности для count-темы), `rank_product_axis_col` (silent одна ось без
люка), leader-текст/atom.

Замечание к контракту «один путь»: `_settle_axis` в шапке пишет
«Без silent rerank», но при rank всё ещё зовёт `rank_axis_resolve`, где
есть и model-pick, и rerank, и автопри одной оси — это и есть скрытый
осевой выбиратель на полигоне onepath.

---

## Замки (тесты), задевающие зону

| Тест | Символы |
|---|---|
| `test_axis_count_plain.py` | `count_question_skips_axis`, `question_wants_breakdown`, `total_question_skips_axis`, `rank_intent_from` |
| `test_b9_routing.py` | `count_question_skips_axis` |
| `test_terminal_round.py` | `total_question_skips_axis`, `question_wants_breakdown` |
| `test_rank_axis_anchor.py` | `rank_intent_from`, `rank_question_text`, `total_*`, `rank_leader_answer_text`, `rank_axis_pick`/`resolve` |
| `test_rank_leader_path.py` | `rank_axis_*`, `rank_leader_*`, `rank_period_clarify_applies` |
| `test_unit_from_data.py` | `rank_leader_answer_text`, `rank_leader_atom` |
| `test_measure_menu_not_silent.py` | `rank_axis_resolve` |
| `test_entity_form.py` | `rank_intent_from`, `count_theme_code_pick_applies` |
| `test_k6_rank_v2.py` | `count_theme_code_pick_applies`, `rank_period_clarify_applies` |
| `test_wiki_card_hybrid.py` / `test_named_type_filter.py` / `test_wiki_candidate_verify.py` | stub `"rank_intent_from"` в словаре |

---

## Краткие выводы для этапа-2

1. Зону **нельзя выкинуть** при flip на один путь: 246 строк / 10 символов
   уже на горячем `_settle_axis` + wiki/sales/stock ветках.
2. Legacy-only символов **нет** — снос legacy сам по себе z10 не чистит.
3. Кандидаты на вырезание после замков: мёртвые **176** строк
   (`rank_leader_*`, `try_rank_period_clarify`+хвост, `count_theme_code_pick_applies`,
   `rank_product_axis_col`).
4. Для «один путь» критичен скрытый осевой выбиратель
   `rank_axis_resolve` — либо увести выбор оси в wiki-меню до SQL, либо
   явно оставить как единственный кодовый settle оси ранга.
