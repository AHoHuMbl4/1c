# P2: независимая линза — системные промпты тракта ask

Срез: 12.09.2026. Только чтение исходников `ubuntu/serenedb/ask/*.py`.
Чужие отчёты `docs/audit/onepath/*` не читались. Модель/БД не звались.

Контекст тракта (приказ «один путь»): вопрос → вики-интерпретация → SQL →
меню прочтений (если >1) → выбор человека → ответ. Меню — единым построителем
**до** SQL; `ask_back` после compose снесён (в live legacy уже глушится).

Живой прод пока на `z20_ask_main_http_legacy` (новый `z20` — заглушка B2).
Промпты общие для зон; оценка — и к live, и к целевой формуле.

---

## Как каждый промт вызывается (факты кода)

| Промт | Определение | Вызов | User-часть |
|---|---|---|---|
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` (и legacy) | `_coverage_answer` → `ds_chat` | `question` + блок `Census:` (итоги + TOP потерянных entity) |
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | `parse_intent` (`z02_intent.py:666`) | `today=YYYY-MM-DD` + `Question: …` |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | только `clarify_text` | `Question` + `Options:` (label + typical) |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | `refuse_text` (z04/z13/z20/z21/legacy) | сырой `question` |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | `rank_axis_pick` ← `rank_axis_resolve` | вопрос (+kind) + `Axes:\n1. …` |
| `ANSWER_SYS` | `z18_compose.py:55` | `compose` ← legacy `answer` (~4109) | `QUESTION` + ROWS/GROUPS + COMPUTED-плейсхолдеры |

**Вызовы `clarify_text(` в дереве ask: 0** (только определение). Живое меню —
`clarify_say` / `format_clarify_options` / `wiki_menu_captions` **без LLM**.

**Поле `ask` в `ANSWER_SYS`:** парсится `_ask_back` (`z18:638`), подставляется
`_filled_ask`, в legacy затем **всегда** обнуляется
`diag["ask_back_dropped"] = "bare_clarify_forbidden"` (legacy ~4325–4327).
Клиенту не уходит. Новый z20 compose не зовёт. После B4 потребитель поля —
только мёртвый код `_ask_back` / `_filled_ask`, если его не вырежут.

---

## Гейт чисел и claims-роли

### `gate(text, rows, agg, …)` (`z20` / legacy)

Сверяет **токены цифр в тексте**, не JSON-claims. Белый список:

- `thresholds` / `our_dates` (наши фильтры);
- при `slot_mode=="list"`: числа из показанных строк (текст/дата/amount);
- из `agg` по `slot_mode`: `count` | `sum`/`min`/`max`/`avg` | rank-группы
  (`value`/`count`/`leader`/…) | compare;
- годы/компоненты известных дат.

`gate_out` = `gate` + `prompt_leak` по `OUR_PROMPTS`.

### `check_claims(claims, agg, totals)` (`z19`)

Роли: **`total`→`agg.sum`**, **`count`→`agg.count`**, **`max`**, **`min`**.
На основном ответе промт велит `claims` = null → сверка **noop**; роль числа
держат плейсхолдеры + `copied_figures` + `asked_figure_missing` + `gate`.

### Coverage-исключение

`COVERAGE_SYS` **заполняет** `claims.total` / `claims.count`
(`n_lost` / `ent_lost`). Там `check_claims` живой + отдельно `gate(text, …)`
по числам переписи. Расхождение с `ANSWER_SYS` («claims ignored») — намеренное
по двум путям, не баг одного промта.

---

## Таблица аудита (блок × ось)

| Блок | Ось | Вердикт | Дословная строка / фрагмент | Риск |
|---|---|---|---|---|
| **ANSWER_SYS** схема `"ask"` | ЛИШНЕЕ | чистить | `"ask": "one clarifying question, or null"` | После сноса ask_back поле не уходит клиенту; модель всё ещё тратит токены и может увести смысл в `ask` вместо `text`. Снос схемы без вырезания `_ask_back` — косметика. |
| **ANSWER_SYS** абзац про `ask` | ОПАСНОЕ | чистить | `"ask" is the middle road between answering and giving up…` … `put in "ask" a single short question` | Прямо конфликтует с «меню до SQL / без встречного вопроса после compose». В live уже глушится кодом; в промте приглашение остаётся. |
| **ANSWER_SYS** `claims` null | ЛИШНЕЕ (частично) | оставить | `"claims" — leave every role null. It exists only for compatibility and is ignored.` | Убрать поле из JSON без правки `_split_answer`/совместимости — риск поломки разбора. Ролевая сверка на основном пути и так не через claims. |
| **ANSWER_SYS** NEVER WRITE FIGURE | ЛИШНЕЕ vs механизм | оставить | `NEVER WRITE A COMPUTED FIGURE YOURSELF…` | Слова дырявы (`[замер 04.08]` рукопись цифрами); защита — плейсхолдеры/`copied_figures`/`gate`. Снос фразы **без** механизма — риск роста рукописи. |
| **ANSWER_SYS** цитаты из строки | оставить | оставить | `Values that appear INSIDE a row… you copy verbatim` | Нужно для list; гейт заземляет на `rows_seen`. |
| **ANSWER_SYS** no data | оставить | оставить | `If the rows do not answer… say plainly that there is no data` | Согласовано с п.21 при пустом множестве; при «есть соседние данные» раньше спасал `ask` — теперь должен спасать **меню до SQL**, не этот абзац. |
| **ANSWER_SYS** `{total}` | оставить | оставить | `state the computed total with {total}` | Согласовано с п.19; user-часть даёт слоты. |
| **ANSWER_SYS** (дыра) | НЕ ХВАТАЕТ | кандидат добавления | — | Нет явного «одно ответное число / не второе число рядом»; «не задавай вопрос после ответа»; «не строй меню здесь». Сейчас частично кодом. |
| **INTENT_SYS** структура | оставить | оставить | блок JSON `terms`/`amount`/`period`/`want`/`measure`/`kind`/… | Живой разбор; вики опирается на `want`/`action_*`/`about`. |
| **INTENT_SYS** measure null | оставить | оставить | `null if the question asks about no quantity` + `want=count when how many records` | Закрывает «count без меры» на стороне смысла; добить кодом (`count_defer`), не промтом. |
| **INTENT_SYS** ALWAYS fill kind | ОПАСНОЕ | чистить (смягчить) | `"kind": "ALWAYS fill this: … Only null if the question names no kind…"` | Давление угадать род записей (п.12). В одном пути род выбирает вики/меню; ложный `kind` сужает поиск. |
| **INTENT_SYS** Never invent | оставить | оставить | `Never invent concepts that are not in the question.` | Контрвес к ALWAYS; оба живут рядом — напряжение. |
| **INTENT_SYS** about coverage | оставить | оставить | `"about": "data"|"coverage"` | Включает `_coverage_answer`; нужен. |
| **INTENT_SYS** (дыра) | НЕ ХВАТАЕТ | не промтом | — | «Интерпретация из вики» — не задача INTENT; отдельный `WIKI_*_SYS` в z21 (вне списка P2). |
| **CLARIFY_SYS** целиком | ЛИШНЕЕ | риск сноса / чистить как мёртвый | весь текст `The question can be answered from several kinds…` | **Нет call sites.** Меню — `clarify_say`+вики-подписи. Снос промта: низкий риск ответов; оставить строку в `OUR_PROMPTS` до удаления функции или наоборот вычистить оба. **Не оживлять** для меню одного пути. |
| **CLARIFY_SYS** Never show table names | (если оживить) | — | `Never show table names, codes or internal identifiers` | Правило уже в коде меню (`label_has_meta_src` / `human_table_label` / wiki captions). |
| **CLARIFY_SYS** (дыра для нового меню) | НЕ ХВАТАЕТ | не сюда | — | Подписи из вики — код `wiki_menu_captions`, не этот промт. |
| **REFUSE_SYS** целиком | оставить | оставить | `Write ONE short sentence… State no facts, no figures…` | Цифры режет код (`_norm_numbers` → пусто). Нужен для п.18 на языке вопроса. |
| **REFUSE_SYS** «cannot… right now» | ОПАСНОЕ (слабое) | оставить с оговоркой | `a verified answer to it cannot be given right now` | Намеренно **не** «нет данных» (коммент z07: отказ бывает при живых данных и провале формулировки). Менять на «нет данных» — врать клиенту. |
| **REFUSE_SYS** (дыра) | НЕ ХВАТАЕТ | нет | — | Для одного пути достаточно; честный no_data — отдельные ветки. |
| **AXIS_PICK_SYS** JSON indices | оставить | оставить | `{"axes": [numbers]}` … `indices only` | Форма держится разбором кода; выдуманные имена отсекаются. |
| **AXIS_PICK_SYS** several numbers | ОПАСНОЕ | чистить под один путь | `Several numbers when different axes would answer different readings… (at most three)` | Множество прочтений → в формуле должно быть **меню человеку до SQL**, а не тихий multi-axis/люк. Промт кормит ветку «несколько осей». |
| **AXIS_PICK_SYS** labels | ОПАСНОЕ (вход) | не промт | user listing: метки с `(%s)` = **имя колонки** (`rank_axis_label_rows`) | В модель уходит техимя оси; в меню осей `distinct_by` тоже col. Риск утечки метаданных в UX — в данных листинга, не в тексте SYS. |
| **AXIS_PICK_SYS** (дыра) | НЕ ХВАТАЕТ | кандидат | — | Нет сигнала «верни пусто / clarify, если два равноправных прочтения» под меню до SQL. |
| **COVERAGE_SYS** JSON+claims | оставить | оставить | `claims.total` / `claims.count` из census | В отличие от ANSWER, claims здесь **сверяются**. Снос claims на coverage — риск ослабить роль-сверку. |
| **COVERAGE_SYS** never recompute | оставить | оставить | `State figures in DIGITS, copied from the census — never recompute` | Дубль с `gate`, но без плейсхолдеров на этом пути слова полезнее, чем на ANSWER. |
| **COVERAGE_SYS** Name the kinds | ОПАСНОЕ | чистить (вход/формулировка) | `Name the kinds of records that are missing… using the reason given` | Census кладёт сырой `entity` — часто техимя. Модель честно перескажет метаданные клиенту (п. подписей). Чинить лучше census/`human_table_label`, не только SYS. |
| **COVERAGE_SYS** (дыра) | НЕ ХВАТАЕТ | слабо | — | Нет «не показывай внутренние имена таблиц» — симметрия с CLARIFY; на coverage сейчас дыра. |

---

## Вердикт по каждому промту (сводка)

### 1. `COVERAGE_SYS` — **оставить как есть**, точечный кандидат

- Не трогать: JSON-форму, claims.total/count, «цифры из census», язык вопроса.
- Кандидат: запрет внутренних имён / требование человеческих ярлыков **или** (лучше) нормализация имён в census до вызова модели.
- Риск сноса claims: сломать единственный путь, где `check_claims` реально работает.

### 2. `INTENT_SYS` — **оставить**, смягчить `ALWAYS fill kind`

- Не трогать: want/measure/period/amount/about/action_*/terms-правила, «never invent».
- Чистить: давление `ALWAYS fill this` на `kind` → формулировка «null, если род не назван; не угадывай» (согласовать с вики-каскадом).
- Риск смягчения kind: больше null → больше нагрузки на вики/поиск; зато меньше ложных сужений (п.12/21).

### 3. `CLARIFY_SYS` — **риск сноса (мёртвый)**

- Удалить или не трогать до вычищения `clarify_text`: на ответы не влияет (0 вызовов).
- **Не** использовать снова для меню одного пути — меню уже кодом + вики.
- Риск «оставить»: ложный ориентир при переписывании тракта («есть же clarify-промт»).

### 4. `REFUSE_SYS` — **оставить как есть**

- Не трогать. Цифры режет код. Смысл «verified answer» vs «no data» осознан.
- Риск переформулировки под «нет данных»: ложный отказ при наличии цифр.

### 5. `AXIS_PICK_SYS` — **чистить под один путь** (осторожно)

- Не трогать: только индексы, пустой список, запрет invent names.
- Чистить/сузить: ветку «several numbers / different readings» → одно число или пусто; развилка прочтений — меню до SQL (код `rank_axis_resolve` + clarify), не список осей в тишине.
- Риск: если live люк/alts завязан на multi-pick, сужение промта без правки resolve даст чаще «первая ось»/rerank — нужен замер rank-вопросов.

### 6. `ANSWER_SYS` — **чистить блок `ask`**, остальное оставить

- Удалить/обнулить: поле `"ask"` в схеме + абзац «middle road…» (строки ~59–69 в `z18_compose.py`).
- Не трогать: ONLY rows, плейсхолдеры, язык, claims-null, запрет выдумки имён/дат, `{total}` для «how much in all».
- Кандидат добавления (коротко, без промт-правил-вместо-кода): «do not ask a follow-up; do not list a second computed figure outside placeholders».
- Риск сноса `ask`: в live нулевой (уже `bare_clarify_forbidden`). Риск переформулировки NEVER WRITE: без плейсхолдеров — регресс рукописи.

---

## Кандидаты правок (конкретные строки)

Только кандидаты; любой merge — только с замером (промпты живые).

1. **ANSWER_SYS** — вырезать из схемы `"ask": …` и абзац:
   - `"ask" is the middle road between answering and giving up… in their own words.`
   - заодно вычистить мёртвые `_ask_back` / `_filled_ask` и legacy-клей (отдельный коммит кода, не только промт).
2. **ANSWER_SYS** — опционально одна строка: no follow-up question; one computed quantity via placeholders only (если код меню/слотов ещё не закрывает класс).
3. **INTENT_SYS** — заменить давление `ALWAYS fill this` у `kind` на «null if unnamed; do not guess».
4. **AXIS_PICK_SYS** — заменить:
   - `Several numbers when different axes would answer different readings of the same question (at most three).`
   - на: одно число при ясном совпадении; иначе `[]` (развилка — не здесь).
5. **CLARIFY_SYS** — удалить константу + `clarify_text` **или** оставить с пометкой dead; не подключать к меню.
6. **COVERAGE_SYS** — добавить «use plain business names; never paste internal table/entity codes» **после** того, как census отдаёт человеческие ярлыки (иначе модель не из чего брать).

---

## Не трогать (без отдельного замера и нужды)

| Что | Почему |
|---|---|
| `REFUSE_SYS` целиком | Короткий, без цифр, язык вопроса; цифры режет код |
| `INTENT_SYS`: want/measure/period/amount/about/action_*/terms | Живой контракт разбора; вики и SQL от них зависят |
| `INTENT_SYS`: count ↔ measure null | Уже закрывает «count без меры» на смысле |
| `ANSWER_SYS`: плейсхолдеры / copy row fields / claims-null / same language | Держит п.19 вместе с `compose`+гейтом |
| `ANSWER_SYS`: «NEVER WRITE A COMPUTED FIGURE» | Слова слабые, но снос без механизма вреден; механизм важнее |
| `COVERAGE_SYS`: claims.total/count + copy digits | Единственный claims-путь с живой `check_claims` |
| `AXIS_PICK_SYS`: JSON indices only / empty list / no invent names | Форма уже заземлена кодом |
| `CLARIFY_SYS` как источник меню | Уже не источник; меню — код |

---

## Итог линзы

1. Главный дефект промптов относительно одного пути — **`ANSWER_SYS.ask`**: связан со снесённым/заглушенным ask_back, приглашает вопрос после ответа, клиенту уже не доезжает.
2. **`CLARIFY_SYS` мёртв** (0 вызовов); новое меню прочтений промптом не обслуживается и **не должно** — подписи из вики кодом.
3. **`AXIS_PICK_SYS` multi-reading** тянет в тихий выбор оси вместо меню до SQL.
4. **`INTENT_SYS.ALWAYS kind`** — давление на догадку рода записей против вики/п.12.
5. Числа на основном пути держит **не** claims, а плейсхолдеры+`gate`+постпроверки; claims живы в **coverage**.
6. Чего «не хватает» для меню/count-без-меры в SYS-списке P2 — почти ничего критичного в промтах: меню и count — зона кода; дыры — в давлении kind/ask/multi-axis и в техименах coverage/осей на **входе** модели.
