# P3: независимая линза — системные промпты тракта ask

Срез: статический разбор исходников 12.09. Чужие отчёты `docs/audit/onepath/*` не читались.
Код и git не менялись; модель и БД не вызывались.

## Как промпты реально зовутся (факт кода)

| Промт | Определение | Вызов | User-часть |
|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | `z02_intent.py` → `msgs` + `_one_intent` | `today=YYYY-MM-DD\n\nQuestion: …` |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | `rank_axis_pick` | `{question} ({kind})?\n\nAxes:\n1. …` |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | только внутри `clarify_text` | `Question: …\n\nOptions:\n- label (typical: …)` |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | `refuse_text` (z20 coverage fallback, z13, z21, z04, legacy no_data) | сырой `question` |
| `ANSWER_SYS` | `z18_compose.py:55` | `compose` → `ds_chat` | QUESTION + ROWS/GROUPS + COMPUTED/{total|count|…} + опц. coverage/measure/folders/corrections |
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` (и копия в legacy) | `_coverage_answer` | `{question}\n\nCensus:\n…` |

Дополнительно (вне списка задачи, но рядом): `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS` в `z21_wiki_choice.py` — вики-каскад; в эту линзу не входят.

Все шесть входят в `OUR_PROMPTS` (`z20*:755`) для `prompt_leak` (точное совпадение длинной строки).

### Живой статус механизмов, связанных с промптами

1. **`clarify_text` / `CLARIFY_SYS`:** вызывающих `clarify_text(` в дереве ask **нет** (только определение). Живое меню — `clarify_say` / `format_clarify_options` (**без модели**): нумерованные «N. вопрос: Подпись? — hint».
2. **`ask` / ask_back:** в legacy после `compose` поле читается `_ask_back`, но затем **безусловно** обнуляется (`ask_back_dropped = bare_clarify_forbidden`, `z20_ask_main_http_legacy.py:4325-4327`). Ветка возврата `kind=clarify` с `ask_back` после этого **мертва**. Новый `z20_ask_main_http.py` — заглушка B2 (`answer` → unavailable); compose/ask_back там ещё нет.
3. **После B4 (один путь):** потребителя поля `ask` у ответа compose **нет**. Модель может всё ещё писать `ask` в JSON (схема в промте), но до человека оно не доезжает. Риск сноса схемы: модель начнёт вкладывать уточнение в `text`.

### `gate()` и роли claims (факт кода)

`gate(answer, rows, agg, thresholds, our_dates, money, slot_mode)` в `z20` — **не** сверка claims-ролей. Она:

- собирает whitelist чисел из `thresholds`, строк (`slot_mode=="list"`), ключей `agg` в зависимости от `slot_mode` (`count` / `compare` / `sum` / `rank` / fallback), дат строк + `date_min`/`date_max` + `our_dates` (+ день/месяц/год границ);
- токенизирует **текст** ответа и отклоняет числа вне whitelist; даты — отдельно.

Роли `claims.total|count|max|min` сверяет **`check_claims`** (`z19_answer_check.py:168`): `total↔agg.sum`, `count↔agg.count`, `max/min↔agg` (или любая из `totals`).

На основном ответе `ANSWER_SYS` велит оставлять claims null → `check_claims` часто no-op; смысл ролей держат **плейсхолдеры + `_fill_figures` + `copied_figures` + `asked_figure_missing`**, а не claims. На coverage — наоборот: промт **требует** заполнить `claims.total`/`claims.count`, и `_coverage_answer` зовёт и `check_claims`, и `gate` по цифрам переписи.

---

## Таблица по осям

Колонки: **блок** (промт / фрагмент) | **ось** (ЛИШНЕЕ / НЕ ХВАТАЕТ / ОПАСНОЕ) | **вердикт** | **дословная строка** | **риск**

### 1. ANSWER_SYS (`z18_compose.py:55-95`)

| блок | ось | вердикт | дословная строка | риск |
|---|---|---|---|---|
| JSON-поле `"ask"` + абзац «middle road» | ЛИШНЕЕ | **чистить** (кандидат): убрать поле и абзац про ask — механизм снесён кодом (`bare_clarify_forbidden`); после B4 потребителя нет | `"ask": "one clarifying question, or null"` и абзац `"ask" is the middle road between answering and giving up…` | Модель может перенести уточнение в `"text"` → ложный «второй акт» без меню/options. Нужен замер: доля ответов с непустым ask / вопросы в text до и после |
| `"claims" — leave every role null…` | ЛИШНЕЕ | **оставить** (пока): схема совместимости; на основном пути claims игнорируются намеренно | `"claims" — leave every role null. It exists only for compatibility and is ignored.` | Снос без правки парсера/`check_claims` — низкий; путать с COVERAGE_SYS (там claims обязательны) |
| `NEVER WRITE A COMPUTED FIGURE` + placeholders | — | **не трогать** | `🔴 NEVER WRITE A COMPUTED FIGURE YOURSELF…` | Снос → рост рукописных цифр; гейт ловит наличие, не роль (`copied_figures` / F285) |
| Цитаты из одной строки vs арифметика | — | **не трогать** | `Values that appear INSIDE a row… you copy verbatim` | Снос → либо отказ копировать номера/даты, либо путаница с итогами |
| Язык / no invent / no_data / `{total}` for totals / short | — | **не трогать** (ядро п.21/19) | `- Reply in the SAME language…` … `- When the question is about an amount… {total}` | Ослабление → молчаливые списки вместо итога или выдумки |
| Меню прочтений до SQL | НЕ ХВАТАЕТ | **не в этот промт**: меню уже кодом (`clarify_say`); ANSWER — после SQL | — | Дописывать «спроси до ответа» в ANSWER_SYS — **опасно** (дубль ask_back) |
| Count без меры / одно число | НЕ ХВАТАЕТ | частично закрыто user-частью `compose` (`{count}` при `slot_mode` count/list); в SYS нет явного «одна величина — одно число» | — | Кандидат **мягкой** добавки только после замера «два итога в одном text»; не дублировать то, что уже в COMPUTED body |
| Приглашение уточнять после ответа | ОПАСНОЕ | то же, что блок `ask` выше | `Fill it ONLY when the rows do not answer exactly… put … in "ask"` | В новом тракте уточнение = меню **до** SQL; post-compose вопрос ломает формулу |

**Вердикт по промту:** чистить кандидат — блок `ask` (схема + 2 абзаца + «ask too» в language-rule). Остальное — не трогать без замера.

### 2. COVERAGE_SYS (`z20_ask_main_http.py:736-750`)

| блок | ось | вердикт | дословная строка | риск |
|---|---|---|---|---|
| Цифры DIGITS из census + claims.total/count | — | **оставить как есть** для ветки coverage: здесь числа **показываются** модели (census), claims реально сверяются | `State figures in DIGITS, copied from the census` / `Put the number of missing rows in "claims.total"` | Снос claims → `check_claims` пустеет; опора останется на `gate` по тексту (уже есть) |
| Нет плейсхолдеров `{total}` | НЕ ХВАТАЕТ / расхождение с ANSWER | **не унифицировать слепо** с ANSWER: у coverage другой контракт (цифры в user уже даны) | — | Перенос «только placeholders» без смены `_coverage_answer` сломает ответы о полноте |
| `Name the kinds… using the reason given` | — | **оставить** | `Name the kinds of records that are missing, and say WHY` | Снос → обезличенные итоги без причин |
| Перечисление entity в census (user, не SYS) | ОПАСНОЕ (косв.) | не промт, а тело: в census попадают имена entity из `search_coverage` | (user) `"%s: %s in source…"` | Метаданные 1С в ответе — если модель копирует entity as-is; держится не SYS, а тем, что кладут в census |

**Вердикт:** оставить как есть. Не смешивать с ANSWER_SYS про claims=null.

### 3. INTENT_SYS (`z01_infra_trace_llm.py:800-846`)

| блок | ось | вердикт | дословная строка | риск |
|---|---|---|---|---|
| Схема terms/amount/period/want/measure/kind/about/action_* /search_form | — | **не трогать**: живой разбор шага 1; поля едут в поиск/фильтры/ветки | весь JSON-шаблон | Урезание поля (kind, about, want) ломает маршрутизацию без видимой ошибки в промте |
| `about: coverage` | — | **оставить** (ветка переписи) | `"coverage" when it asks about the SYSTEM's knowledge` | Снос → coverage-вопросы уйдут в data-поиск |
| `measure` null если нет quantity | — | **оставить** (опора count без меры) | `null if the question asks about no quantity` | Ужесточение «всегда measure» → ложные sum |
| Меню прочтений / wiki | НЕ ХВАТАЕТ | **не в INTENT**: интерпретация — z21; INTENT — структура для SQL после выбора | — | Пихать «выбери прочтение» в INTENT — догадка до вики (п.12) |
| `Never invent concepts` / роли не в terms | — | **не трогать** | `Never invent concepts that are not in the question` / ROLE → kind | Ослабление → terms-шум и ложный AND |

**Вердикт:** оставить как есть. Для «одного пути» дыр в SYS нет — ступени меню/вики не его зона.

### 4. CLARIFY_SYS (`z07_rrf_vectors.py:285-292`)

| блок | ось | вердикт | дословная строка | риск |
|---|---|---|---|---|
| Весь промт | ЛИШНЕЕ | **чистить / вывести из живого контура**: `clarify_text` **нигде не зовётся**; меню строит код | `Ask the person ONE short question… Describe each option in plain business words… Never show table names` | Удаление константы из `OUR_PROMPTS` ослабит leak-детектор только для мёртвого текста; сам файл/функцию лучше не сносить до явного B-волны (на случай отката). Риск сноса **нулевой для ответов**, пока вызывающих нет |
| Подписи без метаданных | — | смысл **уже** в коде (`label_has_meta_src` / `human_table_label` в `format_clarify_options`) | `Never show table names, codes or internal identifiers` | Правило на промте здесь дубль механизма |

**Вердикт:** кандидат на пометку «мёртвый / не звать»; не править текст «по вкусу». Живое поведение меню от этого промта **не зависит**.

### 5. REFUSE_SYS (`z07_rrf_vectors.py:317-320`)

| блок | ось | вердикт | дословная строка | риск |
|---|---|---|---|---|
| Одна фраза, без фактов/цифр/причин | — | **не трогать** | `State no facts, no figures, no reasons, no apologies` | Снос → отказы с «объяснениями» и цифрами; код `_norm_numbers` режет цифры, но не выдуманные причины |
| Язык вопроса | — | **не трогать** | `in the SAME LANGUAGE as the question` | — |
| Не говорит «данных нет» | — | **оставить намеренно** (коммент над промтом: отказ бывает и при данных, когда не прошла формулировка) | (промт) `verified answer … cannot be given` | Замена на «no data» → ложь клиенту (п.21) |

**Вердикт:** оставить как есть.

### 6. AXIS_PICK_SYS (`z10_rank.py:136-147`)

| блок | ось | вердикт | дословная строка | риск |
|---|---|---|---|---|
| JSON `{"axes":[numbers]}` only | — | **не трогать** | `Reply with indices only; naming totals or inventing axis names is outside this step` | Снос → свободный текст/имена колонок в ответе модели |
| Несколько осей = разные прочтения | — | **оставить** (сигнал для clarify осей кодом) | `Several numbers when different axes would answer different readings` | Согласуется с меню прочтений; не путать с ask_back |
| User listing с `lab (col)` | ОПАСНОЕ (данные, не SYS) | не промт: `rank_axis_label_rows` дописывает имя колонки | (код) `"%s (%s)" % (lab, col)` | Модель видит метаданные колонки; в ответ человеку оси обычно не копируются как текст SYS, но список в user нарушает дух «без имён метаданных» для **этого** шага |
| Меню до SQL | НЕ ХВАТАЕТ | выбор оси — всё ещё модельный индекс, не wiki-меню; для B это зона кода `rank_axis_resolve`, не дописывания в SYS | — | Расширять SYS «спроси человека» — снова модельное уточнение мимо единого построителя |

**Вердикт:** оставить SYS. Кандидат правки **не промта**, а формата listing (без сырого `col`) — отдельный замер.

---

## Итог

### Кандидаты правок (со строками; только с обоснованием)

1. **ANSWER_SYS — снести блок ask (высокий приоритет для «одного пути»)**  
   - Удалить из схемы: `"ask": "one clarifying question, or null",`  
   - Удалить абзац: `"ask" is the middle road between answering and giving up… Never ask about our database…`  
   - В language-rule убрать хвост: `— "ask" too`  
   - Обоснование: ask_back уже убит кодом (`bare_clarify_forbidden`); в формуле один путь уточнение = меню до SQL; поле кормит мёртвый `_ask_back` и провоцирует post-answer вопрос.  
   - Обязательный замер: доля JSON с непустым ask; доля `text`, оканчивающихся «?»; gate_ok / kind до-после.

2. **CLARIFY_SYS / `clarify_text` — вывести из контура (низкий риск ответов)**  
   - Не переписывать текст. Кандидат: не держать как «живой» шаг; при волне B — либо оставить только в `OUR_PROMPTS` для истории leak, либо удалить вместе с мёртвой функцией одним коммитом.  
   - Обоснование: zero callers; меню = `clarify_say`.

3. **(Опционально, не SYS) `rank_axis_label_rows`** — не суффиксировать сырой `col` в listing для AXIS_PICK.  
   - Не правка AXIS_PICK_SYS; отдельный замер качества выбора оси.

### Не трогать

| Промт / блок | Почему |
|---|---|
| ANSWER_SYS: placeholders / NEVER WRITE FIGURE / row quotes / language / no invent / `{total}` | Держит п.19; замерено (step6_live, F285); код подставляет числа |
| ANSWER_SYS: `claims` null на основном пути | Сознательно; роль закрыта слотами + `asked_figure_missing` |
| COVERAGE_SYS целиком | Другой контракт; claims+digits согласованы с `_coverage_answer` |
| INTENT_SYS целиком | Живой контракт разбора; count без measure уже разрешён |
| REFUSE_SYS целиком | Согласован с `_norm_numbers` и п.18; «no data» в отказе было бы ложью |
| AXIS_PICK_SYS целиком | Узкий индексный шаг; несколько осей = сигнал неоднозначности |
| Добавки в ANSWER/INTENT про «меню прочтений» | Меню уже кодом; промт-правило сюда — регресс к ask_back |

### Краткие вердикты по шести промптам

| # | Промт | Вердикт |
|---|---|---|
| 1 | COVERAGE_SYS | **оставить как есть** |
| 2 | INTENT_SYS | **оставить как есть** |
| 3 | CLARIFY_SYS | **мёртвый контур** — не править текст; кандидат снятия вместе с `clarify_text` |
| 4 | REFUSE_SYS | **оставить как есть** |
| 5 | AXIS_PICK_SYS | **оставить как есть** (listing col — отдельно от промта) |
| 6 | ANSWER_SYS | **чистить кандидат: блок `ask`**; остальное не трогать |

### Замечание о прод/новом z20

Новый `z20_ask_main_http.py` пока не исполняет compose (заглушка B2). Промпты живут в зонах z01/z07/z10/z18 и в **legacy**-пути, который сейчас и есть прод до flip. Аудит относится к **живым константам**, которые flip унаследует; правка ANSWER_SYS затронет legacy немедленно после выката файла зоны.
