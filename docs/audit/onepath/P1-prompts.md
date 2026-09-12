# P1: независимая линза — системные промпты тракта ask

Срез: 12.09.2026. Только чтение исходников `ubuntu/serenedb/ask/*.py`.
Чужие отчёты `docs/audit/onepath/*` не читались. Модель / БД не звались.

## Как устроено использование (факты кода)

| Промт | Определение | Вызов | User-часть |
|---|---|---|---|
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` (и legacy) | `_coverage_answer` → `ds_chat` | `question` + блок `Census:` (итоги + top потерянных сущностей) |
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | `parse_intent` (`z02_intent.py:666`) | `today=YYYY-MM-DD` + `Question: …` |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | **вызовов `clarify_text(` в ask/ нет** | было бы `Question` + `Options:` label/distinct_by |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | `refuse_text` → no_data / gate-fail ветки (`z20`, `z13`, `z21`, `z04`…) | только текст вопроса |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | `rank_axis_pick` | вопрос (+kind) + нумерованный список осей |
| `ANSWER_SYS` | `z18_compose.py:55` | `compose` → `ds_chat` | `QUESTION` + ROWS/GROUPS + COMPUTED-слоты (значения скрыты) |

Контекст тракта на момент среза:

- Новый `z20_ask_main_http.py`: `answer()` — заглушка `unavailable` до B3; flip в runtime — B6. Живой ответный путь — **legacy** (`z20_ask_main_http_legacy.py`), там `compose`/`ANSWER_SYS` ещё живы.
- Меню уточнений человеку строит **код** (`clarify_say` / `format_clarify_options` в z20), не `CLARIFY_SYS`.
- Поле `"ask"` из JSON ответа: парсится `_ask_back` (`z18:638`); в legacy после гейта **сбрасывается** (`bare_clarify_forbidden`, ~4325). Других потребителей поля `ask` после compose нет. После приказа одного пути deliverable ask_back мёртв; парсер и промт ещё живы.
- Вне списка шести: `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS` (`z21_wiki_choice.py`) — фактические промпты выбора прочтения до SQL. В шести системных их нет.

### Гейт чисел и claims-роли

`gate()` (`z20:78`): белый список цифр из `thresholds` + строк (только `slot_mode=list`) + агрегата по `slot_mode` (`count` / `sum` / `rank` / `compare` / list). **Роли claims не читает** — смотрит только цифры в тексте.

`check_claims()` (`z19:168`): роли `total`→`agg.sum`, `count`→`agg.count`, `max`, `min` — **только если модель заполнила поле**.

| Путь | claims реально сверяются? |
|---|---|
| Coverage | да: промт велит `claims.total` / `claims.count`; + `gate(text)` по census |
| Compose-ответ (legacy) | нет: `ANSWER_SYS` велит оставить claims null; роль держит `{total}`/`asked_figure_missing`, не `check_claims` |
| `slot_mode=count` | в `gate` из agg разрешён только `count` (не sum/min/max) — «одно число» держится кодом |

---

## Таблица по блокам (6 промптов × 3 оси)

| Блок | Ось | Вердикт | Дословная строка (или якорь) | Риск |
|---|---|---|---|---|
| **COVERAGE_SYS** схема JSON + claims | ЛИШНЕЕ | оставить (не дубль ANSWER) | `"claims": {"total":…,"count":…}` + «Put the number of missing rows in "claims.total"…» | На coverage claims — единственная ролевая сверка; снос → останется только `gate` по множеству цифр census (роль «итог vs число видов» ослабнет) |
| **COVERAGE_SYS** «copied… never recompute» | ЛИШНЕЕ / держится кодом | оставить как пояснение модели | `State figures in DIGITS, copied from the census — never recompute, never estimate.` | Правило уже в `gate`; фраза дешёвая; снос без замера не нужен |
| **COVERAGE_SYS** «Name the kinds… WHY» | НЕ ХВАТАЕТ? | оставить | `Name the kinds of records that are missing, and say WHY, using the reason given.` | Имена сущностей приходят из census (не выдумка); список top ограничен `COVERAGE_TOP` |
| **COVERAGE_SYS** про меню / count без меры | НЕ ХВАТАЕТ | не в зоне промта | — | Coverage — ветка `about=coverage`, не меню прочтений |
| **COVERAGE_SYS** | ОПАСНОЕ | низкий | те же «copied from census» | Обход только если цифры в тексте ∈ census, но роль перепутана и claims пусты — частично ловит `check_claims` при заполненных claims |
| **INTENT_SYS** целиком | ЛИШНЕЕ | **оставить как есть** | весь блок Rules + схема | Разбор уже чинит код типами (`z01` после промта); промт — форма для модели; живые прогоны `intent_parse_bench` |
| **INTENT_SYS** `measure` null / `want=count` | НЕ ХВАТАЕТ | уже есть | `null if the question asks about no quantity` + `want=…count` | Для «count без меры» достаточно; отдельной фразы «не выдумывай меру» нет — риск выдуманной меры ловится позже выбором колонки, не этим промтом |
| **INTENT_SYS** прочтения вики до SQL | НЕ ХВАТАЕТ | не здесь | — | Выбор сущности/прочтения — `WIKI_*_SYS` + код; INTENT даёт `kind`/`action_class`/`search_form` как вход |
| **INTENT_SYS** | ОПАСНОЕ | контролируемый | `Never invent concepts that are not in the question.` | Изобретение `terms`/`kind` — известный разброс; держится согласием прогонов + памятью, не промтом |
| **CLARIFY_SYS** целиком | ЛИШНЕЕ | **мертвый путь** | весь `CLARIFY_SYS` + `clarify_text` | Вызовов нет; меню = `clarify_say`. Снос промта: убрать из `OUR_PROMPTS` только вместе с решением про leak-детектор; иначе безвредный мёртвый текст |
| **CLARIFY_SYS** «plain business words… Never show table names» | НЕ ХВАТАЕТ в живом меню | перенесено в код | `Never show table names, codes or internal identifiers.` | В живом пути: `label_has_meta_src` / `human_table_label` в `format_clarify_options` |
| **CLARIFY_SYS** | ОПАСНОЕ | если снова подключат | `Describe each option in plain business words…` | Модель могла бы дописать факты; сейчас не зовётся |
| **REFUSE_SYS** целиком | ЛИШНЕЕ | **оставить** | `State no facts, no figures…` | Цифры всё равно вырезает `_norm_numbers` в `refuse_text`; фраза согласована с кодом |
| **REFUSE_SYS** «не говорить нет данных» | НЕ ХВАТАЕТ? | уже учтено комментарием | промт: `could not produce a verified answer` (не «no data») | Верно для gate-fail при живых данных (п.21); снос формулировки → риск лжи «данных нет» |
| **REFUSE_SYS** | ОПАСНОЕ | низкий | — | Пустой отказ при сбое сети — fallback вызывающего |
| **AXIS_PICK_SYS** целиком | ЛИШНЕЕ | **оставить** | короткий JSON `{"axes":[numbers]}` | Уже минимален; индексы чинит код |
| **AXIS_PICK_SYS** несколько осей = разные прочтения | НЕ ХВАТАЕТ / частично есть | оставить | `Several numbers when different axes would answer different readings… (at most three).` | Это оси GROUP BY **после** выбора сущности, не wiki-меню до SQL |
| **AXIS_PICK_SYS** | ОПАСНОЕ | низкий в промте | `Reply with indices only; naming totals or inventing axis names is outside this step.` | Утечка техимён — скорее в `rank_axis_label_rows` (`label (col)`), не в SYS |
| **ANSWER_SYS** поле `"ask"` + абзац middle road | ЛИШНЕЕ / ОПАСНОЕ | **чистить (кандидат)** | схема: `"ask": "one clarifying question, or null"`; абзац `"ask" is the middle road…`; `- Reply… — "ask" too.` | После одного пути ask_back снесён приказом; legacy всё равно дропает. Риск сноса: модель перенесёт уточнение в `text` → нужен замер compose. Кто ещё читает `ask` после B4: только `_ask_back`/`_filled_ask`; deliverable нет |
| **ANSWER_SYS** `"claims" — leave every role null` | ЛИШНЕЕ | чистить осторожно / оставить null-compat | `"claims" — leave every role null. It exists only for compatibility and is ignored.` | На compose `check_claims` не спасает; схема дублирует COVERAGE. Снос поля из JSON — риск поломать `_split_answer`/ожидания приборов, если где-то ждут ключ |
| **ANSWER_SYS** NEVER WRITE COMPUTED FIGURE | держится кодом | **оставить** | `NEVER WRITE A COMPUTED FIGURE…` + placeholders | Замер 04.08: промт дыряв ~1/8; держат слоты + рукопись + gate. Снос фразы без замены — регресс рукописи |
| **ANSWER_SYS** «closely related… ask» vs «say no data» | ОПАСНОЕ | чистить вместе с ask | `Fill it ONLY when the rows do not answer exactly…` vs `If the rows do not answer… say… no data` | Прямо приглашает post-answer clarify (против формулы одного пути: меню до SQL) |
| **ANSWER_SYS** «one answer / count» | НЕ ХВАТАЕТ частично | усилить user-слотами, не SYS | есть: `state the computed total with {total} — listing… instead… is not an answer` | `slot_mode=count` и белый список gate уже в коде compose-body; в SYS нет явного «одно главное число / без второго» |
| **ANSWER_SYS** меню прочтений до SQL | НЕ ХВАТАЕТ | не зона ANSWER | — | До SQL — wiki/clarify_say; в ANSWER упоминать меню = смешение ступеней |

---

## Вердикт по каждому промту

### 1. `COVERAGE_SYS` — оставить как есть
Живой узкий путь. Claims здесь не «совместимость», а реальная ролевая сверка + `gate` по census. Чистка «never recompute» ради вкуса не оправдана: дёшево и согласовано с кодом. Меню/count-без-меры к этому промту не относятся.

### 2. `INTENT_SYS` — оставить как есть
Форма JSON + правила разделения terms/kind/measure — вход в вики и отбор. Поведение стабилизировано кодом согласия прогонов и типами; любое переформулирование — только с `intent_parse_bench`. Для новых ступеней одного пути отдельных дыр в этом промте нет (дыры — в `WIKI_*` и построителе меню).

### 3. `CLARIFY_SYS` — риск сноса низкий; кандидат на удаление как мёртвый
`clarify_text` нигде не вызывается; живое меню — `clarify_say` (данные → строки, затем `gate_out`). Промт остаётся в `OUR_PROMPTS` для `prompt_leak`. **Не трогать** до явного решения: (а) удалить константу + функцию + запись в `OUR_PROMPTS`, или (б) оставить как мёртвый якорь leak. Возвращать вызов модели для меню — против приказа «единый построитель ДО SQL» и текущего кода.

### 4. `REFUSE_SYS` — оставить как есть
Короткий, согласован с вырезанием цифр кодом и с тем, что отказ ≠ «данных нет». Нужен на многих ветках. Чистить нечего осмысленного.

### 5. `AXIS_PICK_SYS` — оставить как есть
Уже индекс-only. «Несколько осей = разные прочтения» полезно для меню осей rank (код при ≥2). Не путать с wiki-прочтениями до SQL. Правка подписей осей — в `rank_axis_label_rows`, не в SYS.

### 6. `ANSWER_SYS` — чистить блок `ask` (кандидат); остальное оставить
- **Удалить / обнулить (дословные якоря):**
  1. В схеме JSON: `"ask": "one clarifying question, or null",`
  2. Абзац: `"ask" is the middle road between answering and giving up. … in their own words.`
  3. В буллетах: `— "ask" too.` (из строки про язык)
  4. Зафиксировать в JSON `"ask": null` навсегда **или** убрать ключ — после решения, читает ли `_ask_back` ещё кто-то на flip; сейчас deliverable уже запрещён.
- **Оставить:** запрет рукописных итогов + placeholders; язык ответа; «no data» когда строки не про вопрос; требование `{total}` на «how much in all».
- **Не раздувать SYS** правилами «меню до SQL» / «одно число» — это уже `clarify_say`, wiki-каскад и `gate(slot_mode=…)`. Промт-правила сюда = нарушение «правила не промтом».

Обоснование чистки `ask` не вкус, а расхождение с приказом одного пути и с кодом: legacy всё равно ставит `ask_back=""` (`bare_clarify_forbidden`); новый z20 compose не зовёт. Пока абзац жив, модель тратит токены на middle road и может увести смысл ответа в «частичный ответ + вопрос».

---

## Кандидаты правок (конкретные строки)

| # | Промт | Действие | Строки / якорь | Замер обязателен |
|---|---|---|---|---|
| C1 | `ANSWER_SYS` | удалить поле и абзац `ask` (middle road) | `z18_compose.py` схема `"ask":…`; абзац `"ask" is the middle road…`; хвост `— "ask" too.` | да: compose на корпусе приёмки (нет ли уточнений внутри `text`; gate/figures без регресса) |
| C2 | `ANSWER_SYS` | после C1: упростить `_ask_back` / legacy ветку ask_back до no-op или сноса | потребители только legacy | да на flip B; до flip — можно не трогать код пути |
| C3 | `CLARIFY_SYS` | удалить константу + `clarify_text` + из `OUR_PROMPTS` | `z07:285-311`; списки в z20/legacy | низкий риск deliverable; проверить `prompt_leak` тесты |
| C4 | (вне 6) | не смешивать: аудит `WIKI_PICK_SYS`/`WIKI_VERIFY_SYS` отдельно | `z21:45-57` | — |

Не кандидат: переписывать `INTENT_SYS` / `REFUSE_SYS` / `AXIS_PICK_SYS` / тело `COVERAGE_SYS` / блок `NEVER WRITE A COMPUTED FIGURE` без отдельного замера и без новой дыры в коде.

---

## Список «не трогать»

1. `INTENT_SYS` — целиком (форма + Rules).
2. `REFUSE_SYS` — целиком.
3. `AXIS_PICK_SYS` — целиком.
4. `COVERAGE_SYS` — claims.total/count + census-копирование + язык ответа.
5. `ANSWER_SYS` — блок запрета рукописных итогов и контракт placeholders `{total}`/`{count}`/named slots.
6. `ANSWER_SYS` — требование отвечать на языке вопроса (без хвоста про ask).
7. Живой построитель меню `clarify_say` (не возвращать `CLARIFY_SYS` в тракт).
8. Поведение `gate(slot_mode=count)` и вырезание цифр в `refuse_text` — это код, не промт.

---

## Итог линзы

Главный дефект среди шести — **не мёртвый `CLARIFY_SYS`**, а **живой абзац `ask` в `ANSWER_SYS`**: он описывает снесённый ask_back и приглашает уточнять *после* ответа, тогда как контракт одного пути требует меню прочтений *до* SQL и один ответ без «второго числа/вопроса». Остальные пять: либо уже минимальны и держатся кодом (`REFUSE`, `AXIS_PICK`, `COVERAGE`), либо слишком дорогие для косметики (`INTENT`), либо уже вытеснены кодом (`CLARIFY`). Пробелы «меню до SQL» и «count без меры» в этих шести почти не лечатся — они закрыты (или должны закрываться) `WIKI_*`, `clarify_say` и `slot_mode`/`gate`, а не новыми долженствованиями в SYS.
