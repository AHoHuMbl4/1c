# W1 — карта живости `ask/z02_intent.py`

Дата съёмки: 12.09.2026. Метод: AST верхнего уровня зоны + `rg`/`\bимя\b` по
`ubuntu/serenedb/ask/*.py` и `ubuntu/serenedb/test_*.py` (включая f-строки /
`getattr` / строковые ключи); импорт-структуры нет — только фактические
упоминания имён в общем namespace после `_bootstrap` + `register_zone`.

Файл зоны: `ubuntu/serenedb/ask/z02_intent.py` — **713** строк, **26**
символов верхнего уровня (сумма span-ов символов = **625**; остальное —
шапка, комментарии, `register_zone`).

Загрузка: `_bootstrap.py` включает `"z02_intent.py"` (после z01, до z03…;
z20 — последним, new или legacy по `ASK_ONEPATH`). `_imports.py` /
`_wire.py` символов зоны не упоминают (только `apply_bindings` /
`register_zone` внутри самой зоны).

## Затенение (важно для вердикта)

После z02 грузится `z16_veto_pick_entity.py` и **перезаписывает** в общем
namespace:

| Имя | z02 | победитель |
|---|---|---|
| `question_expects_accounting_data` | def :361–394 | **z16:329** |
| `_NON_DATA_MARKERS` | const :208–211 | **z16:323** |

Имя `question_expects_accounting_data` зовут новый тракт (через z21) и
legacy — но исполняется **тело z16**, не z02. Константа `_NON_DATA_MARKERS`
из z02 после загрузки z16 не читается; живой `_creative_non_data_question`
(z02) в рантайме видит уже маркеры z16.

---

## Таблица символов

| Символ | Строки (span) | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `_json_blocks` | 28 (9–36) | внутри: `_first_intent_object`; тесты: `test_intent.py:78–93` | **ЖИВА НОВОМУ** (транз. ← `parse_intent`) |
| `_intent_text` | 12 (39–50) | внутри: `_normalize_intent`, `_intent_terms/date/…`, `conversational_*`; **вне**: `z12_stock_balance.py` (много: 21,116,151,166,…); `z21_wiki_choice.py:83,240,734,795,989,1006,1055`; тесты `test_intent.py` + стабы в wiki/named_type тестах | **ЖИВА НОВОМУ** (прямо транз. ← `parse_intent`; также ← z21 ← new `answer`) |
| `_intent_number` | 17 (53–69) | внутри: `_normalize_intent`; **вне**: `z14_clarify_memory.py:207` (`answers_diverge`); `z16_veto_pick_entity.py:228,235` (`same_number`); `test_intent.py:114–120` | **ЖИВА НОВОМУ** (← `parse_intent`). Внешний хвост z14/z16 → `answers_src_conflict` / `mute_measure_blocks` **не зовутся** из new/legacy z20 (только определения + тесты) |
| `_intent_date` | 14 (72–85) | внутри: `_normalize_intent`; `test_intent.py:123–130` | **ЖИВА НОВОМУ** |
| `_intent_terms` | 37 (88–124) | только внутри: `_normalize_intent` (внешних упоминаний нет) | **ЖИВА НОВОМУ** |
| `_intent_word` | 3 (127–129) | внутри: `_normalize_intent`; **вне**: `z12_stock_balance.py:1110` (`_stems_of_text`) | **ЖИВА НОВОМУ** |
| `same_concept_groups` | 40 (156–195) | внутри: `parse_intent:676`; комментарий legacy `z20_…_legacy.py:2160` (не вызов); `test_intent.py:319+`; `test_solr_synonyms_apply.py` | **ЖИВА НОВОМУ** |
| `_stem_set` | 8 (198–205) | внутри: `same_concept_groups`; **вне**: `z12:1106`; **legacy** `z20_…_legacy.py:2140,2170` (прямой вызов в `answer`); `test_intent.py:326` | **ЖИВА НОВОМУ** (через `parse_intent`; плюс прямой legacy) |
| `_NON_DATA_MARKERS` | 4 (208–211) | определение z02 **затенено** z16:323; вызов имени — из z16.`question_expects…` и (после затенения) из z02.`_creative_non_data_question` | **МЁРТВА** (определение z02 не исполняется) |
| `_CONVERSATIONAL_HOW` | 2 (215–216) | внутри: `conversational_business_vague` | **ЖИВА НОВОМУ** |
| `_creative_non_data_question` | 3 (219–221) | внутри: `conversational_business_vague`, z02.`question_expects…` (мёртвое тело); живой путь — через enrich | **ЖИВА НОВОМУ** |
| `_accounting_word_known_to_base` | 6 (224–229) | внутри: `conversational_*` / `_intent_has_*` / `_intent_coordinates_empty` | **ЖИВА НОВОМУ** |
| `_intent_has_known_accounting_anchor` | 16 (232–247) | внутри: `conversational_business_vague` | **ЖИВА НОВОМУ** |
| `_intent_coordinates_empty` | 15 (250–264) | внутри: `conversational_business_vague` | **ЖИВА НОВОМУ** |
| `_base_business_topic_words` | 32 (267–298) | внутри: `_enrich_conversational_business`, z02.`question_expects…` (мёртвое) | **ЖИВА НОВОМУ** (← enrich ← `parse_intent`) |
| `conversational_business_vague` | 37 (301–337) | внутри: `_enrich_conversational_business`; `test_intent.py:466+` | **ЖИВА НОВОМУ** |
| `_enrich_conversational_business` | 19 (340–358) | внутри: `parse_intent:681` | **ЖИВА НОВОМУ** |
| `question_expects_accounting_data` | 34 (361–394) | имя зовут: **new-путь** `z21_wiki_choice.py:907` (`try_wiki_hybrid_entity_pick`); **legacy** `z20_…_legacy.py:1868`; `z16:299` (свой же shadow); тесты K4/wiki/stock. Исполняется **z16**, не z02 | **МЁРТВА** (определение z02 затенено) |
| `_base_knows_kind_or_measure` | 25 (397–421) | внутри: `_normalize_intent`, `_accounting_word_*`; **вне**: `z12:654,657,1122,1136`; тесты intent/stock/warehouse | **ЖИВА НОВОМУ** |
| `_normalize_intent` | 139 (424–562) | внутри: `_one_intent`; `test_action_class.py:42` | **ЖИВА НОВОМУ** |
| `_one_intent` | 17 (565–581) | внутри: `parse_intent` | **ЖИВА НОВОМУ** |
| `_field_key` | 2 (584–585) | внутри: `_field_lead`, `_merge_intents` | **ЖИВА НОВОМУ** |
| `_field_lead` | 9 (588–596) | внутри: `parse_intent`, `_merge_intents` | **ЖИВА НОВОМУ** |
| `_merge_intents` | 25 (599–623) | внутри: `parse_intent` | **ЖИВА НОВОМУ** |
| `parse_intent` | 61 (626–686) | **new** `z20_ask_main_http.py:1873,1878` (`answer`); **legacy** `z20_…_legacy.py:1758,1762`; тесты `test_intent.py`, `test_compose.py`, `test_stock_balance_path.py`, `test_trace_rid.py` (stub) | **ЖИВА НОВОМУ** |
| `_first_intent_object` | 20 (689–708) | внутри: `_one_intent` | **ЖИВА НОВОМУ** |

---

## Итог зоны

| Вердикт | Символов | Строк (span) |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 24 | **587** |
| **ЖИВА ТОЛЬКО LEGACY** | 0 | **0** |
| **МЁРТВА** (затенение z16) | 2 | **38** |
| **Всего символов** | 26 | **625** |
| Файл целиком | — | 713 |

**Вердикт по зоне:** зона **нужна одному пути**. Единственная точка входа
нового z20 — `parse_intent`; через неё транзитивно живы почти все помощники
разбора. Символов «только legacy» нет (`_stem_set` в legacy ещё и прямо, но
уже жив новому через `same_concept_groups`). Мёртвы как определения z02
только два имени, затёртые z16.

---

## Транзитивные цепочки (до корня z20)

### Главная (новый + legacy)

```
parse_intent
  ← z20_ask_main_http.py:answer:1873/1878          [НОВЫЙ]
  ← z20_ask_main_http_legacy.py:answer:1758/1762   [LEGACY]

parse_intent
  → _one_intent → _first_intent_object → _json_blocks
  → _one_intent → _normalize_intent
        → _intent_terms → _intent_text
        → _intent_date → _intent_text
        → _intent_number
        → _intent_word
        → _base_knows_kind_or_measure
  → _merge_intents → _field_key, _field_lead
  → _field_lead (отрыв прогонов)
  → same_concept_groups → _stem_set
  → _enrich_conversational_business
        → conversational_business_vague
              → _CONVERSATIONAL_HOW
              → _creative_non_data_question → (_NON_DATA_MARKERS имя; после load = z16)
              → _intent_coordinates_empty → _accounting_word_known_to_base → _base_knows…
              → _intent_has_known_accounting_anchor → …
              → _intent_text
        → _base_business_topic_words
```

### Доп. цепочки в новый тракт (не через `parse_intent`, усиливают живость)

```
_intent_text ← z21_wiki_choice (wiki_action_axis / wiki_verify_* / …)
  ← try_wiki_hybrid_entity_pick / wiki-каскад
  ← z20_ask_main_http.py:answer                    [НОВЫЙ]

_intent_text / _base_knows_kind_or_measure / _intent_word / _stem_set
  ← z12_stock_balance.*
  ← answer (new и legacy; stock-ветви)

_stem_set ← z20_…_legacy.py:answer:2140,2170       [только LEGACY прямо]
```

### Имя живое новому, тело — не z02

```
question_expects_accounting_data  (исполняется z16)
  ← z21:try_wiki_hybrid_entity_pick:907
  ← new answer / wiki-каскад
  ← legacy answer:1868
```

Тело z02:`question_expects_accounting_data` (с веткой
`conversational_business_vague` + `_base_business_topic_words`) **ниоткуда
не зовётся** после загрузки z16.

---

## Bootstrap / imports / wire

| Файл | Упоминание зоны |
|---|---|
| `_bootstrap.py:24` | `"z02_intent.py"` в `_ZONE_FILES` |
| `_imports.py` | нет имён зоны |
| `_wire.py` | нет имён зоны |
| конец зоны | `register_zone('ask.z02_intent', globals())` |

---

## Тесты (замки, касающиеся зоны)

| Файл | Что трогает |
|---|---|
| `test_intent.py` | основной замок зоны: `_json_blocks`, `_intent_*`, `same_concept_groups`, `_stem_set`, `conversational_business_vague`, `question_expects_accounting_data`, `parse_intent`, memo |
| `test_solr_synonyms_apply.py` | `same_concept_groups` (Ф6.3) |
| `test_k4_clarify_vs_nodata.py` | `question_expects_accounting_data` |
| `test_action_class.py` | `_normalize_intent` |
| `test_compose.py` / `test_stock_balance_path.py` / `test_trace_rid.py` | `parse_intent` (часто stub) |
| `test_stock_balance_path.py` / `test_warehouse_aggregate_breakdown.py` | `_base_knows_kind_or_measure` (stub) |
| wiki/named_type/verify_* | стабы `_intent_text` / `question_expects_accounting_data` для изоляции z21 |

---

## Скрытые выбиратели, доступные НОВОМУ тракту

Зона не выбирает **src/таблицу**. Но через обязательный `parse_intent` в новый
`answer` код **молча фиксирует прочтение** полей интента (до вики-меню):

1. **`_normalize_intent` / `_intent_text`** — при `kind`/`measure` списком
   берётся **первый** элемент; остальные уходят в `fixed` («alternatives»),
   человеку меню не строится. Это выбор меры/рода кодом из ответа модели.
2. **`_merge_intents` + `_field_lead`** — голосование по прогонам: победитель
   поля (kind/measure/period/…/action_axis) выбирается отрывом, не человеком.
3. **`_base_knows_kind_or_measure`** внутри `_normalize_intent` — решает,
   вычищать ли слово из `terms` как «род/мера» (словарь базы). Меняет
   координаты отбора без меню.
4. **`same_concept_groups`** — сливает группы терминов по стеммеру/синонимам
   движка (расширяет ИЛИ внутри понятия).
5. **`_enrich_conversational_business`** — на разговорном «как…» **принудительно
   ставит `want=count`** и кладёт `parse.conversational_topics` из
   `_base_business_topic_words(3)` (темы базы). Это кодовый сдвиг want/тем
   до SQL/вики.

Пункты 1–2 и 5 — ближайшие к классу «скрытый выбиратель прочтения»
(мера/род/want), попадающие в новый тракт транзитивно. Отдельного
выбирателя **источника** в зоне нет.

---

## Краткий ответ на «нужна ли зона одному пути»

**Да.** Новый `z20_ask_main_http.answer` прямо зовёт `parse_intent`; без зоны
нет шага «интерпретация вопроса». После flip legacy снос зоны невозможен:
«только-legacy» строк = 0. Кандидаты на вычистку внутри зоны после полного
сноса legacy и сверки с z16 — лишь затенённые **38** строк
(`question_expects_accounting_data` + `_NON_DATA_MARKERS` определения z02),
и то как мёртвый дубль, не как отключение разбора.
