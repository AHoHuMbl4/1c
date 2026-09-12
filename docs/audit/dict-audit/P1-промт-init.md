# P1 — Промт инициализации словаря (v2)

Дата: 13.09.2026 (cursor, **read-only** по коду; отчёт — проект).  
Вход: `00-СВОДКА.md`, `B5-промты.md`, `A2-синонимы.md`, `B3-застрявшие.md`, `A4-объяснения.md`;  
текущий текст — `ubuntu/serenedb/wiki_alias.sh:182` (= добор величин `:240` = reask `:397`).  
Коммитов нет. Код/`wiki_alias.sh` не менялся.

Модель-адресат: **Qwen3.8-27B** (thinking off). Схема JSON — **прежняя**, менять нельзя.

---

## Вердикт

Ниже — готовый английский каркас промта инициализации. Он закрывает дыры аудита:
синонимы = речь спрашивающего + роли из `flows` (без title); явные запреты;
лимиты 3–8 / 1–3 слова; `bestUsedFor` = короткие шаблоны вопросов; `notEnoughFor` =
тематическое «не я» + соседский редирект без `,` и `()`; «сомневаешься — не пиши»;
один few-shot на EN с правилом «язык ответа = язык title».

---

## 1. Готовый текст промта (дословно)

Вставить вместо строки `printf` на `:182` / `:240` / `:397` (байт-в-байт один текст).
После промта — как сейчас — JSON пачки из select/reask (`entity`, `title`,
`quantities`, `flows`).

```
JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. Answer language for every string field = the language of that record's title (the English example below is STRUCTURE ONLY — never copy its language into the output when the title is in another language).

For EACH record:

(1) aliases — ONLY everyday words a person actually puts in a question when they mean THIS kind of record (their spoken asking-words). ALSO include ROLE words for every flow listed in the input for this record: the same catalog is named differently by role depending on the flow (structure example: a counterparty catalog → buyers in sales flows, suppliers in purchase flows); take roles ONLY from the listed flows — do not invent flows. Limits: 3 to 8 aliases; each alias is 1 to 3 words; no sentences; no question words alone (how/how many/what/who as standalone tokens). Do NOT add the title (or a morphological variant of the title) as an alias — the title is already known from input. Quantity names and field names go ONLY under quantities, never under aliases.

BANS for aliases (skip the token if unsure): platform meta-labels and their equivalents in the title language (list, catalog, directory, types, kinds, register, journal, document, classifier, form, report as a meta-word); case/number/inflection variants of the SAME stem (pick one citation form); Latin-script words when the title is not Latin; words that equally fit a sibling in THIS batch (leave those out of aliases — put the distinction in notEnoughFor); jargon opaque to a non-developer.

(2) quantities — for EVERY name from the input quantities list, copy that name EXACTLY and give 1-5 short names a person uses for that value (a noun, or a noun with the action/event word they say — e.g. spoken event forms for money totals), 1-3 words each, no sentences. Same bans as aliases. If a listed quantity has no clear everyday name, return it with an empty aliases array.

(3) bestUsedFor — 2 to 4 short question TEMPLATES this record truly answers (the shape of what a person asks). No foreign topics (do not advertise price-list / stock-balance / customer-count questions for a record that does not answer them). No office jargon gerunds. Prefer spoken wording over metadata wording.

(4) notEnoughFor — two kinds of short strings, both required when applicable: (a) THEMATIC "not me" — topic labels a person might confuse with this record but that this record does NOT answer (stock balances, price list, customer list/count, cash, payroll, … — only topics that are plausible confusions for THIS title); (b) SIBLING redirect — for each easy-to-confuse sibling from THIS input list, one short string: sibling title then what THAT sibling answers instead. Hard format rule for EVERY notEnoughFor string: no commas and no parentheses inside the string (downstream stores arrays as comma-CSV). Use a dash or the word "not"/"see" instead. Prefer 3-8 strings total. If unsure whether a topic is a real confusion — omit it.

Global: if you are not sure a token or claim is correct — do not write it (omit; never guess). Do not invent quantities, flows, or sibling names that are not in the input.

One structure example (English skeleton only; rewrite all strings into the title language of each real item):
{"entity":"catalog_counterparties","aliases":["buyers","suppliers","customers"],"quantities":[{"name":"Count","aliases":["headcount","how many partners"]}],"bestUsedFor":["how many customers","who bought this month"],"notEnoughFor":["not stock balances","not price list","Organizations - our own companies not trading partners"]}

Schema: {"items":[{"entity":"...","aliases":["..."],"quantities":[{"name":"<exact from input quantities>","aliases":["..."]}],"bestUsedFor":["..."],"notEnoughFor":["..."]}]}. Input: 
```

---

## 2. Недостаток старого → как закрыт в новом

| Недостаток (аудит) | Источник | Как закрыт в v2 |
|---|---|---|
| Промт просит «also the record title itself» → падежи/склейки имени | B5 §2, A2 §шум, сводка №1 | Явный запрет: title и его морфология **не** alias; лимит 3–8 разных обиходных основ |
| Мета-ярлыки платформы (список/справочник/типы/…) в aliases | A2 топ-коллизий, сводка №1 | BAN-блок: meta-labels + «equivalents in the title language» |
| Нет запрета падежей одного слова | B5 §3.2, A2 | BAN: case/number/inflection of the SAME stem — одна citation form |
| Нет запрета латиницы при русском title | A2 (кassa…), B5 | BAN: Latin-script when title is not Latin |
| Слова, подходящие соседям пачки, остаются в aliases | B5 init (дыра), A2 каша | BAN: words that equally fit a sibling → не в aliases; различие в NEF |
| `bestUsedFor` = «the questions it answers» → канцелярит / чужие темы («установка цен» у номенклатуры) | A4, B4, сводка №3 | 2–4 short question TEMPLATES; «No foreign topics»; запрет gerund-канцелярита |
| `notEnoughFor` ≈ только siblings (96%) — нет тематического «не я» | B5 §3.1, A4 §3, B3 | Два рода: (a) thematic not-me, (b) sibling redirect — оба обязательны when applicable |
| Фразы NEF со скобками/запятыми ломают `str_split` CSV | B1 (30 строк) | Hard rule: no commas and no parentheses inside each NEF string |
| Нет «сомневаешься — не пиши» | B5 дыра №2 | Global omit-if-unsure; пустой `aliases` у quantity при неясности |
| Few-shot один EN без правила языка | B5, сводка (хотели «на языке базы») | Один EN skeleton + явная строка: answer language = title language; never copy example language |
| Роли по flows были — сохранить | замер 28.08, B5 «что хорошо» | Сохранены; усилено: ONLY listed flows, do not invent |
| Лимит синонимов не задан | B5 | 3–8 aliases; 1–3 words each |
| Глаголы-события (наторговали…) нигде | B3 | В `quantities`: «noun with the action/event word»; в `bestUsedFor`: spoken question templates — не в entity-aliases как вопросы целиком (урок 05.08) |
| Имена величин утекали в entity aliases | wiki_alias.sh коммент 25.08 | Повторено: quantity/field names ONLY under quantities (код-фильтр остаётся) |

Схема JSON и поля (`entity` / `aliases` / `quantities[]` / `bestUsedFor` / `notEnoughFor`) — без изменений.

---

## 3. Риски: что 27B может понять не так

| Риск | Почему вероятен | Смягчение вне этой задачи |
|---|---|---|
| Всё равно положит title / склонение в aliases | Старая привычка из few-shot эпох + title рядом во входе | Код-фильтр: отсев токенов = title/label (P2/мета-стоп); force-переген |
| Скопирует английский пример при русском title | Few-shot на EN; модель зеркалит | Первая строка промта + «never copy its language»; приёмка метрикой A3 на живом журнале |
| Опустошит поля из-за «if unsure omit» | 27B осторожничает → пустые aliases → MERGE нечему писать / skip | На песочнице смотреть долю пустых; при массовой пустоте смягчить формулировку, не лимиты |
| Склеит thematic + sibling в одну строку с запятой | Привычка к перечислениям | Hard rule в промте; пост-фильтр CSV (P4) — не здесь |
| «not stock balances» напишет у всего подряд | Переусердствует с тематическим NEF | «only topics that are plausible confusions for THIS title» + omit if unsure |
| Role word = соседское слово (например общее «товары») | Конфликт «роли из flows» vs «не слова соседей» | При равенстве — BAN соседа побеждает; роль только если отличает этот поток |
| Event-глаголы уедут в entity aliases целиком как вопросы | B3 давит на «наторговали» | Промт кладёт event forms в quantities / BUF-шаблоны; entity aliases — имена вида записи, не целые вопросы |
| Meta-слова на языке title не узнает по EN-списку | Универсальность: бан на EN-каркасе | Кодовый стоп-словарь платформы 1С после генерации (сводка проект №2) — не промтом-только |
| Проигнорирует лимит 3–8 | Модели слабо держат счёт | Parse/trim до 8 в коде (будущее); сейчас только промт |
| Sibling redirect без title из пачки / выдуманный сосед | Галлюцинации имён | «Do not invent … sibling names that are not in the input» |
| BUF снова протащит чужую тему узким шаблоном | Как «установка цен» у номенклатуры | Явный «No foreign topics»; красная приёмка на прайс/остатки/клиенты (A4-кейсы) |

---

## 4. Вне скоупа P1 (не проектировать здесь)

- Формат хранения CSV / починка `str_split` — **P4** (в промте только запрет `,`/`()`).
- Код-фильтр мета-слов после генерации — сводка проект №2.
- `WIKI_ALIAS_FORCE` / перезапись живых строк — сводка №3; без этого v2 не обновит бой.
- Коллизионный промт (`:312`) — отдельная задача; там сейчас **законсервированы** общие слова.
- Temperature/seed — B5 §4; не часть текста промта.

---

## 5. Источники

- `docs/audit/dict-audit/00-СВОДКА.md` (проект улучшения п.1)
- `docs/audit/dict-audit/B5-промты.md` (дословный старый промт, дыры)
- `docs/audit/dict-audit/A2-синонимы.md` (коллизии мета-слов, латиница, шум)
- `docs/audit/dict-audit/B3-застрявшие.md` (event-глаголы, остатки/склад)
- `docs/audit/dict-audit/A4-объяснения.md` (BUF-ложь прайс, NEF без thematic)
- `docs/audit/dict-audit/B1-конвейер-полей.md` (CSV/скобки)
- `ubuntu/serenedb/wiki_alias.sh:162–182` (комменты 05.08 / 25.08 / 28.08 + текущий printf)
