# Линза-2 (волна C «один путь»): интент и словарь — карта мест смерти вопроса

Режим: только чтение. Источники: `z01_infra_trace_llm.py`, `z02_intent.py`;
цепочка после интента — вызовы из тех же слотов (`answer` / wiki / probe), с file:line.
Мнений нет; «не найдено» — явно.

---

## §1 Пайплайн интента (слоты, LLM, бюджеты)

### 1.1 Точка входа

| шаг | file:line | факт |
|---|---|---|
| `answer` зовёт разбор | `z20_ask_main_http.py:3689` | `intent = parse_intent(question, today)` |
| разбор | `z02_intent.py:635-695` | `parse_intent(question, today)` — к базе/данным шаг не обращается (докстринг 636) |

### 1.2 LLM-вызовы в тракте интента (z01 + z02)

| что | file:line | модель / промт / бюджет | fail |
|---|---|---|---|
| тело запроса | `z01:529-541` `_ds_chat_body` | `DS_MODEL` (`DEEPSEEK_MODEL`, умолч. `deepseek-v4-pro`, `z01:213`); `temperature=0`; `max_tokens` снаружи | — |
| HTTP | `z01:544-555` `ds_chat_post` | `DS_BASE + /v1/chat/completions`; `urlopen(..., timeout=120)` | при `deadline_hit()` → `AskDeadline` (546-547) |
| обёртка | `z01:558-559` `ds_chat` | возвращает `content` или `None` | — |
| промт интента | `z01:752-798` `INTENT_SYS` | JSON-слоты: terms, amount, period, want, measure, kind, about, action_class, action_axis, search_form | — |
| 1-й прогон | `z02:574-576` `_one_intent` | `ds_chat(msgs, max_tokens=INTENT_MAX_TOKENS)` | — |
| 2-я попытка при пустом JSON | `z02:584-587` | тот же msgs + assistant[:400] + «Return the JSON object.» | — |
| нет объекта после 2 попыток | `z02:588-589` | `raise RuntimeError("модель не вернула разбор вопроса")` | **блокирующий** (не fail-soft) |
| согласие N прогонов | `z02:677-681` | пока `len(samples) < INTENT_SAMPLES` и отрыв `< INTENT_LEAD` | — |

Бюджеты/env (z01):

| имя | file:line | умолч. |
|---|---|---|
| `ASK_INTENT_MAX_TOKENS` → `INTENT_MAX_TOKENS` | `z01:840` | 400 |
| `ASK_INTENT_SAMPLES` → `INTENT_SAMPLES` | `z01:841` | 5 |
| `ASK_INTENT_LEAD` → `INTENT_LEAD` | `z01:842` | 3 |
| `ASK_INTENT_MEMO` → `INTENT_MEMO` | `z01:844` | 512 |
| `ASK_INTENT_GROUPS` / `ASK_INTENT_ALTS` | `z01:851-852` | 6 / 6 |
| `ASK_DEADLINE_SEC` (весь запрос, в т.ч. ds_chat) | `z01:21`, проверка `z01:546` | 88 |
| `ASK_STEM_DICT` → `STEM_DICT` | `z01:855` | `search_dict_stem` |
| `ASK_SOLR_SYNONYMS` / `ASK_SOLR_SYNONYMS_DICT` | `z01:858-859` | `"0"` / `""` |

Других LLM в z01/z02 для интента **не найдено**. (Wiki pick/verify — `z21`, не зона интента.)

### 1.3 Слоты после нормализации

`_normalize_intent` (`z02:433-571`) собирает:

| слот | file:line | как |
|---|---|---|
| `terms` | `z02:436`, `_intent_terms` 88-124 | группы написаний; срез → `lost`/`fixed` |
| `kind` / `measure` | `z02:438-444` | `_intent_text` (первое непустое) |
| `search_form` | `z02:449-452` | пусто если >200 симв. или ≡ сырому вопросу |
| выемка kind/measure из terms | `z02:473-484` | только если `_base_knows_kind_or_measure(w)` |
| `want` | `z02:486-491` | whitelist `_WANT_OK` (`z01:826`: list/sum/count); иначе → `"list"` + fixed |
| `about` | `z02:493-494` | data/coverage |
| `period` / `period2` | `z02:496-552` | только ISO `YYYY-MM-DD` (`_intent_date` 72-85); иначе `lost` |
| `amount` | `z02:516-534` | op из `_AMOUNT_OPS` (`z01:833`) |
| `action_class` / `action_axis` | `z02:554-556` | event/object/none |
| `parse` | `z02:569-570` | `{ok, lost, fixed, assumed}` |

После merge: `same_concept_groups` на `terms` (`z02:685-689`), затем `_enrich_conversational_business` (`z02:690`).

### 1.4 Что интент НЕ делает

- Не матчит `measure`/`kind` со словарём при извлечении (кроме выемки известных из `terms`, `z02:473-484`).
- Не пишет «незнакомое слово» в diag/журнал (`z02` — stderr/diag **не найдено**).
- Не возвращает `kind=no_data` (в z02 нет такого return).

---

## §2 Таблица «точек смерти» для незнакомого слова

Условие: слово меры/рода **не** известно базе (`_base_knows_kind_or_measure` → False) и/или нет хита в alias/measure SQL.

| file:line | механизм | условие исхода |
|---|---|---|
| `z02:417-430` `_base_knows_kind_or_measure` | stem×`search_measure_alias` + entity form | нет хита → `False`; при `RuntimeError` → `True` (офлайн fail-open) |
| `z02:473-484` | незнакомое **не** вынимается из `terms` | слово остаётся в `terms` как значение для буквального отбора |
| `z02:167-170` `same_concept_groups` | `ts_lexize(STEM_DICT)` [+ solr dict] | `RuntimeError` → группы **без слияния**, без лога |
| `z02:588-589` | нет JSON от модели | `RuntimeError` → срыв шага 1 (не `no_data`) |
| `wiki_card_hybrid.sql:158-171` `struct_measure` | `ts_lexize(stem_dict, measure)` × `search_measure_alias` | нет совпадения стемов → ветвь пуста (другие ветви пула живы) |
| `wiki_card_hybrid.sql:138-149` `struct_alias` | `alias_idx.aliases @@ question` | редкое слово без алиаса → ветвь не даёт src |
| `z21:1351-1362` | пустой `wiki_hybrid_pool` | `wiki_empty_pool` → `None` или сразу `no_data` (если не accounting) |
| `z21:1321-1330` / `z20:3776-3785` | нет `picked` после каскада | `kind: "no_data"`, `reason=wiki_pick\|wiki_empty_pool\|wiki_no_leader` |
| `z21:1389-1393` | verify/pick `outcome=="none"` | `return None` → тот же `no_data` выше |
| `z14:49-90` `measure_choice` | exact / alias / substring | нет хита → `(None, [], 'rerank')` — **само по себе не no_data** |
| `z20:1550-1561` `_settle_measure` | после miss measure | при `want=="sum"` и `len(names)>1` → **меню мер**, не отказ |
| `z20:3920-3933` | `probe(terms)` + `matched_groups < n_groups` | слово в `terms` без хита в корпусе/резолвере → `no_data`, `reason="значения из вопроса не найдены в данных"` |
| `z06:107-127` `probe` | резолвер только для **terms**-групп | measure/kind сюда не входят |

**В z01/z02 отказ `no_data` за незнакомое слово не оформляется** — только подготовка слотов и (опционально) сохранение слова в `terms`.

---

## §3 Цепочка смерти для «наторговали» (и трёх соседей)

Вопросы: «…наторговали…» / «…наотгружали…» / «…вышло…». Ниже — путь **по коду** при отсутствии словарного хита меры/алиаса. Живой LLM-выход на конкретный вопрос здесь не снимался → слоты `kind`/`measure`/`terms` помечены как «зависит от модели».

### Общая цепочка (все четыре)

1. **`z20:3689`** → `parse_intent`.
2. **`z02:675-676`** msgs: `INTENT_SYS` + `today` + `Question`.
3. **`z02:574-590`** `_one_intent` → `_normalize_intent`.
4. **`z02:473-484`**: если модель кладёт редкое слово в `measure`/`kind`, а `_base_knows_kind_or_measure` = False (`z02:406-430`: нет в entity form и нет строк в `search_measure_alias` по стемам) — слово **остаётся** в слоте; из `terms` **не** вычищается.
5. **`z02:685-689`** `same_concept_groups` только по `terms` (не по measure). Solr-dict при ошибке — молча (`z02:169-170`).
6. **`z02:690`** conversational enrich — для «сколько…» обычно не срабатывает (`question_expects…` уже True через want/regex, `z02:384-399`).
7. **`z20:3767-3772`** `wiki_primary_entity_cascade` / `try_wiki_hybrid_entity_pick`.
8. **`z21:281-308` `_wiki_hybrid_vars`**: в SQL уходит `measure=intent.measure`, `stem_dict=STEM_DICT`, `question=search_form|raw`.
9. **`wiki_card_hybrid.sql:158-171`**: `struct_measure` пуст, если стемов редкого слова нет в `search_measure_alias`.
10. **`wiki_card_hybrid.sql:138-149`**: `struct_alias` не обязан поймать «наторговали»/«наотгружали»/«вышло» в `alias_idx`.
11. Пул = kNN ∪ struct_* (`sql:197-210`). Если после фильтров пусто → **`z21:1351-1362`** → **`z21:1321-1330`** / **`z20:3776-3785`**: **`kind: "no_data"`** (до меню мер и до SQL-ответа).
12. Если пул непуст, но pick/verify → `none` → **`z21:1389-1393`** → тот же `no_data`.
13. Если лидер есть, а редкое слово ещё в **`terms`**: **`z20:3921-3933`** `probe` → unmatched → **`no_data`** «значения из вопроса не найдены».
14. Если лидер есть, слово только в **`measure`**, `want=sum`, мер >1: **`z20:1550-1561`** → **меню мер** (не смерть). На прогоне «умерли отказом» этот исход **не** совпадает с описанным дефектом.

### Слово «наторговали» (два из четырёх вопросов)

| факт | file:line |
|---|---|
| классификатор sales знает подстроку в **тексте вопроса** | `z11_sales.py:35-40` (`"наторговали"`, `"наторгова"`) |
| то же в kind/measure-хелпере | `z11_sales.py:20-23` |
| это **не** словарный хит и **не** вход wiki-SQL | вызывается из `question_expects_accounting_data` (`z02:395`) и sales-маршрутов **после** wiki; пул wiki не расширяет |
| «наотгружали» / «вышло» в этих списках | **не найдено** (`z11_sales.py:35-40` — нет) |

Итог по коду: при miss словаря меры/алиаса вопрос с редким словом доезжает до **`kind: "no_data"`** на wiki-каскаде (`z20:3778-3784` или `z21:1325-1330`) **или** на unmatched `terms` (`z20:3930-3933`), **до** меню прочтений мер/окон, если wiki уже вернул отказ. Пустое меню как отдельный return для этих слов **не найдено**.

---

## §4 Словарные таблицы и конфиг

### 4.1 Env и чтение в ask (z01/z02)

| env | file:line | таблица/объект | роль |
|---|---|---|---|
| `ASK_STEM_DICT` | `z01:855` | умолч. `search_dict_stem` | `ts_lexize` в `same_concept_groups`, `_base_knows_kind_or_measure` |
| `ASK_SOLR_SYNONYMS` | `z01:858` | флаг `"1"` | включает доп. `ts_lexize` |
| `ASK_SOLR_SYNONYMS_DICT` | `z01:859` | имя словаря, **без дефолта** (`""`) | второе `ts_lexize` в `same_concept_groups` (`z02:161-166`) |
| (хардкод SQL) | `z02:423-427` | `search_measure_alias` | известна ли величина |
| (через entity_form) | `z02:418-421` | `search_entity_alias` + `search_tables` (+ `CLASS_TABLE`) | род записей |
| wiki (не z01/z02, но потребляет те же слоты) | `wiki_card_hybrid.sql:138-171` | `alias_idx`, `search_entity_alias`, `search_measure_alias` | кандидаты пула |
| init словарей | `corpus_init.sql:349+` | `search_dict`, `search_dict_stem`, `search_dict_alias_stem`, заготовка `search_dict_syn` | вне ask-зоны |

`search_dict` / `search_dict_syn` **внутри z01/z02 по имени кроме STEM/SOLR env не читаются**.

### 4.2 `ASK_SOLR_SYNONYMS_DICT` указывает на отсутствующую таблицу/словарь

Код пути:

```
z02:161  use_syn = ASK_SOLR_SYNONYMS and bool(ASK_SOLR_SYNONYMS_DICT)
z02:164-166  cols += ts_lexize(ASK_SOLR_SYNONYMS_DICT, …)
z02:168-170  try: psql(...); except RuntimeError: return groups, 0
```

| условие | поведение | file:line |
|---|---|---|
| `ASK_SOLR_SYNONYMS=0` (умолч.) | dict **не вызывается**, даже если имя задано | `z02:161` |
| флаг=1 и имя непустое, объект отсутствует / SQL ошибка | **молчание**: `return groups, 0` — без merge, без stderr, без diag | `z02:169-170` |
| ошибка или деградация наружу | **не найдено** | — |

Итого при аномалии «имя есть, словаря нет» и включённом флаге: **тихая деградация** слияния словоформ; вопрос не падает на этом шаге.

### 4.3 Алиасы вики (связанный контур, не z01/z02)

| объект | где | env |
|---|---|---|
| `search_entity_alias` / `alias_idx` | `wiki_card_hybrid.sql:138-148` | `WIKI_ALIAS_TOP` → `z21:15`, подстановка `z21:306` |
| `search_measure_alias` | `sql:162-169`, `z02:423` | — |
| `STEM_DICT` в wiki vars | `z21:304` | тот же `ASK_STEM_DICT` |

---

## §5 Точки, где доступен полный контекст (вопрос + пул кандидатов)

Критерий: одновременно сырой вопрос **и** пул словаря/карточек с описаниями/алиасами — чтобы отдать LLM-резолверу «где что».

| место | file:line | что есть | чего нет |
|---|---|---|---|
| `parse_intent` / `INTENT_SYS` | `z01:752-798`, `z02:675-676` | только `today` + вопрос | пула словаря/алиасов **нет** |
| `same_concept_groups` | `z02:156-195` | написания `terms` + `ts_lexize` | кандидатов с описаниями **нет**; при ошибке — тишина |
| `_base_knows_kind_or_measure` | `z02:406-430` | count-хит да/нет | список кандидатов наружу **не отдаётся** |
| wiki pick | `z21:1241-1248` | вопрос (+kind) + `wiki_format_card_lines(cards)` (name/description/axes/measures) | это **уже отфильтрованный** пул; незнакомое слово отдельно не маркируется |
| wiki verify | `z21:1180-1189` | вопрос + паспорта | то же |
| `measure_choice` / `_settle_measure` | `z14:49-90`, `z20:1541-1561` | слово меры + имена/алиасы **одной** сущности после wiki | глобального пула словаря мер **нет**; miss → `'rerank'` без журнала слова |
| diag ответа | `z20:3709-3710`, `z21:1349-1350` | `terms`/`kind`/`measure`, `wiki_pool` | поля «незнакомое слово» / «miss alias» в z01/z02 **не найдено** |
| TRACE / TOKENS | `z01:118-122`, `z01:501` | rid/слой/мс/токены; **без текста вопроса** (`z01:68`) | слово не логируется |

**Вывод по z01/z02:** механизма «незнакомое слово + пул кандидатов словаря с описаниями/алиасами → журнал/diag/LLM» **не найдено**. Слово либо остаётся в слотах интента, либо пропадает из структурных веток wiki/SQL без отдельной метки. Ближайшее место с вопросом + описаниями кандидатов — **wiki pick/verify (`z21`)**, уже после сборки пула, не на шаге интента.
)
