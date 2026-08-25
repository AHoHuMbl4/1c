# Класс K5: ответ в atoms есть, наружу отказ (okna)

**Статус:** исполнен 25.08 (`ASK_ATOM_TERMINAL`, md5 **70bc8dab**); выкат на `:8092` — оркестратор (scp `RUNTIME_FLOOR:egress`).  
**Дата:** 2026-08-25  
**Опора:** [`docs/SCORER_CLASSES_2026-08-25.md`](../docs/SCORER_CLASSES_2026-08-25.md)
(класс K5, 2 вопроса), [`docs/PLAN_ANSWER_CONTRACT.md`](../docs/PLAN_ANSWER_CONTRACT.md)
§2 / §3 / §4 / §5 / §6, образец структуры
[`work/rank-path-fix-design.md`](rank-path-fix-design.md),
контур `ubuntu/serenedb/serene_ask.py` (fork → arbiter → gate → figures/refuse).

Объект работы — **класс**, не отдельные эталоны. Слой лечения — детектор /
контракт выдачи атома (§5), не правка gold.

---

## 0. Проблема (живая диагностика 25.08, бой `:18091`)

Полный скорер okna: бой и стейджинг **15/24**, diff вердиктов **0**.
Класс K5 = **2** из 9 FAIL
([`SCORER_CLASSES_2026-08-25.md`](../docs/SCORER_CLASSES_2026-08-25.md) §4).

Повтор `/ask` на бое (Bearer из `/tmp/okna-probe.env`, `user=gold-v2`;
стейджинг `:8092` не трогали):

| # | Вопрос | kind | Цитата ответа / diag (не пересказ) |
|---|---|---|---|
| K5a | сколько документов реализации за декабрь 2025? | clarify | text: `1. …: Справочник партий бланков…?` / `2. …: Наборы документа реализации (фурнитура)…?`; `fork.outcome=unique`; `fork.atoms[0].atom={operation:count, exact_value:307, proof_status:computed, measure_label:«Реализация ТМЦ», period:2025-12-01..2025-12-31}`; `arbiter_detected.кандидаты=[catalog_партиибланков…, document_реализациятмц_фурн_наборы…]`, `числа=[0,0]`; top-level `atom=null` |
| K5b | в этом месяце продали больше, чем в прошлом? | figures | text: `Проверенный ответ на этот вопрос сейчас дать невозможно.`; `atom={operation:compare, exact_value:1755883.45, proof_status:computed, form:compare, src:accumulationregister_реализациятмц}`; `diag.slot_mode=rank`, `axis_form=compare`; `gate_rejected=['величина 1755883.45 не названа цифрами', 'нераспознанное место: {max}…', '{min}…', '{avg}…']`; `figures` без sum/compare — только `date_min/max`, `outside_period`, паспорт |

Эталон корпуса: K5a → **307** (count документов реализации за декабрь 2025);
K5b → diff MTD vs прошлый месяц (форма compare; текущее число атома
**1 755 883.45** ≠ эталон gold — хвост окна/меры внутри compare, но наружу
сейчас отказ, не число).

### Общая причина (слой: детектор / выдача §5)

**Посчитанный `AnswerAtom` (`proof_status=computed`) не является
терминальным контрактом выдачи: после счёта ответ ещё может быть заменён
clarify/refuse слоями, которые смотрят на текст модели / пустой refuse /
круг арбитра по текстовым кандидатам, а не на атом.**

Как бьёт по двум (один механизм, разные выходы):

| Вопрос | Где атом уже есть | Что гасит выдачу |
|---|---|---|
| K5a | `fork.outcome=unique`, atom count=307 | `unique` не early-return (§2 unique «ниже обычный круг»); под-ответ лидера уходит в `mute` (нет непустого text при figures/answer); `answers_diverge` на двух соперниках с пустым/нулевым отпечатком → clarify entity **без** лидера и без 307 |
| K5b | atom compare=1755883.45 после `aggregate_compare_sales` | `answer_slot_mode(form=compare)→rank`; гейт режет прозу (`asked_figure_missing` + пустые `{max/min/avg}`); fallback `kind=figures` + `refuse_text` при пустом `TOTAL_TEXT`; `compose_slot_values(..., slot_mode=rank)` **не кладёт** sum/compare в figures |

Вердикт для лечения: это **защита, гасящая хороший (уже посчитанный) ответ**,
а не защита, правильно остановившая плохие данные. Число в атоме есть;
клиенту уходит молчание / чужой clarify (п. 13 + п. 21 TARGET).

### Что ещё объясняет та же причина

| Класс | Связь |
|---|---|
| **K4** (compare не собран) | другая ранняя развилка (форма не compare). После починки формы тот же баг `slot_mode=rank` + refuse на gate-fail **снова** спрячет diff — K5b уже это показывает на живом compare |
| K1–K3, K6 | не объясняет: там либо неверный атом, либо clarify **до** счёта нужной формы |

**Числа:** общая причина объясняет **2 из 2** вопросов K5; дополнительно
предупреждает регресс K4→K5 после сборки compare.

---

## 1. Данные

### 1.1. Уже есть (не плодить загрузчик)

| Источник | Роль для K5 |
|---|---|
| `fork_scan` / `resolve_fork_outcome` | `unique` + atom в `diag.fork.atoms` (K5a) |
| `aggregate_compare_sales` / `atom_from_agg` | atom compare с `exact_value` (K5b) |
| `render_atom_pair` / `build_answer_atom` | детерминированная пара без модели (§5) |
| `gate` / `asked_figure_missing` / `_fill_figures` | ловят прозу; не обязаны гасить атом |

Новых EntitySet / SQL-загрузчиков нет. Счёт остаётся штатным SQL внутри
SereneDB (как сейчас). Перед кодом с новым SQL — MCP `serenedb-docs`, строка
`Доки:` в коммите реализации.

### 1.2. Слой «прибор»

Дефект прибора как первичная причина K5 — **нет**
([`SCORER_CLASSES_2026-08-25.md`](../docs/SCORER_CLASSES_2026-08-25.md) §4).
Эталон SQL на той же базе; чинить скорер/эталоны под класс запрещено.

---

## 2. Детектор / контракт выдачи

### 2.1. Правило класса (одно)

**Если существует применимый атом с `proof_status=computed` и
`exact_value is not None`, терминальный исход обязан нести это число
человеку** — `kind=answer` / `figures` через `render_atom_pair` (и figures-
слоты), а не `refuse_text` и не entity-clarify, игнорирующий атом.

Место в пайплайне (§3 контракта: детектор после match/preds, до
формулировки; §5: renderer кодом):

```
fork_scan → resolve_fork_outcome
  → [NEW] unique + computed → fork_outcome_unique / render_atom_pair   # K5a
  → A/B/C как сейчас
  → arbiter circle:
        mute с computed atom ≠ «нет ответа»; не clarify только по text-rivals
  → compose / gate
  → [NEW] gate fail + agg/atom computed → render_atom_pair (+ figures с sum)
        а не refuse_text при пустом TOTAL_TEXT                          # K5b
  → slot_mode: form=compare → sum|compare, не rank                      # K5b
```

### 2.2. K5a: `unique` терминален

Сейчас комментарий у исходов: «unique / empty — ниже обычный круг».
Проект: при `_outc == "unique"` и атоме класса `PROOF_COMPUTED` —
вернуть ответ тем же строителем, что исход A (`render_atom_pair`), с
`fork_outcome=unique` в diag. Обычный круг арбитра **не** перетирает
доказанную единственность.

Rivals с `no_live_cells` / count 0 не открывают entity-clarify поверх unique.

### 2.3. K5b: compare ≠ rank в слотах; gate-fail ≠ silent refuse

1. `answer_slot_mode`: `form=compare` → режим, в котором в figures попадает
   `sum` (diff), не `rank` без групп.
2. При `not ok` и наличии `_atom` / `agg` с числом: текст =
   `render_atom_pair(_atom)` (passport кодом), figures =
   `compose_slot_values` с sum; `refuse_text` — только если атома нет.
3. Гейт исходящего **не ослабляется**: вторая попытка и проверка прозы
   остаются; меняется только fallback «структура вместо прозы», который
   комментарий в коде уже обещает, но при пустом `TOTAL_TEXT` отдаёт отказ.

### 2.4. Слои

| Слой | Лечит класс? | Что меняется |
|---|---|---|
| **Данные** | нет как ядро | не требуется знать okna |
| **Детектор / выдача** | **да** | unique→ответ; atom terminal на gate-fail; slot_mode compare |
| **Словарь** | нет | — |
| **Прибор** | нет как причина | после фикса — регрессия 24 |

---

## 3. Исходы A/B/C

Без новой лестницы. Уточнение контракта §2:

| Ситуация | Исход |
|---|---|
| один класс, один src, atom computed | **unique → ответ** (не падение в arbiter clarify) |
| один класс, несколько src, атомы совпали | A (как сейчас) |
| несколько классов, все подписаны | B |
| непосчитанное / неподписанное | C (лидер + «есть другое прочтение» / clarify) |
| gate отверг прозу, atom computed | **figures/answer с парой атома**, не refuse |
| атома нет / scan_error | unavailable / no_data как сейчас |

`ASK_FORK_OUTCOMES` не подменять. Нового выбирающего арбитра нет.

---

## 4. Флаг / умолчание

| Env | Умолч. | Смысл |
|---|---|---|
| `ASK_ATOM_TERMINAL` | `0` | выкл. на бою; 1 = unique→ответ + gate-fail→render_atom_pair + compare slot_mode |

Бой `:8091` этим заходом не включать. Проба — стейджинг после кода (когда
свободен). Имя флага рабочее.

---

## 5. Симметрия: что откроется при починке

Защиты ставились по живым случаям. Ослабление без компенсации — брак.

| Меняем | Что перестанет ловиться само | Чем компенсировано |
|---|---|---|
| unique → ответ без arbiter clarify | ложный unique, если `fork_scan` не посчитал живого соперника (молчаливый неверный src) | замок: при ≥2 live classes с разными атомами — B/C, не unique; оффлайн `test_fork_outcomes`; живой кейс «неверная сущность при уверенном числе» (ALIAS_VETO / writer_pair) остаётся **до** unique только если классов >1 |
| gate-fail → `render_atom_pair` вместо refuse | «отказ вместо чужой прозы» больше не прячет число; клиент увидит число даже при кривой формулировке модели | гейт прозы **не** отключается; wrong-entity по-прежнему ловят fork/ALIAS_VETO/arbiter **до** этого fallback; замок: gate всё ещё режет рукопись (`copied_figures`) на пути ok |
| `slot_mode` compare ≠ rank | модель может снова писать `{max/min/avg}` — они заполнятся, если есть в agg | для compare ключи max/min/avg в known не обязательны; замок: figures.compare/sum присутствует; rank-путь «сколько продали вчера» без регресса |

Исходный случай гейта (проза без цифры → не уходит как «verified answer»
модели) **сохраняется**: меняется только носитель числа (атом/figures), не
разрешение модели писать свои цифры.

---

## 6. Замки

### 6.1. Оффлайн (на шаге кода; новые кейсы рядом с существующими)

Уже в дереве: `test_fork_outcomes.py`, `test_ask_journal.py`,
`test_sales_canon_prefer.py`.

| Замок | Что фиксирует |
|---|---|
| `resolve_fork_outcome` → unique + computed → early answer с exact_value | K5a |
| mute-кандидат с computed atom + text-rivals 0/0 → **не** entity clarify без лидера | анти-регресс arbiter поверх unique |
| `form=compare` → slot_mode не rank; figures содержат sum/diff | K5b слоты |
| gate fail + atom computed → text из `render_atom_pair`, не `refuse_text` | K5b выдача |
| gate всё ещё ловит рукопись / утечку на пути ok | исходный случай гейта |
| sum-путь «сколько продали вчера» без смены kind | регресс §6bis |
| `test_fork_outcomes` / calendar / rank locks зелёные | A/B/C целы |

### 6.2. Живой замок класса (приёмка проекта)

На стейджинге, тот же `ab-gold-okna.tsv` / скорер okna **24** вопроса,
флаг `ASK_ATOM_TERMINAL=1`:

1. **Два вопроса K5 — OK** (или K5b: kind/answer с числом формы compare;
   если число ≠ gold из‑за окна — отдельный хвост compare, но **не** refuse/clarify
   без числа).
2. **Остальные 22 не краснеют** (OK остаются OK).
3. **Замок защиты:** искусственный / оффлайн кейс «проза без цифры при живом
   agg» → не `kind=answer` с рукописью; число только из атома/figures.
4. Оффлайн §6.1 green.

---

## 7. Вопросы в скорер

Новый набор не заводить: класс в
[`SCORER_CLASSES_2026-08-25.md`](../docs/SCORER_CLASSES_2026-08-25.md) и в
`ab-gold-okna.tsv` (декабрь 2025 / compare месяцев). После кода — тот же
`ab_scorer.py`, `AB_CONTOUR=okna`.

---

## 8. Порядок внедрения

### Шаг 1 — оффлайн-замки под проект (без выката)

Кейсы §6.1 красные на текущем коде (ожидаемо).

### Шаг 2 — выдача за `ASK_ATOM_TERMINAL` (умолч. 0)

Точки в `serene_ask.py` (имена уже в дереве): ветка после
`resolve_fork_outcome` для `unique`; блок gate-fail (~figures/`refuse_text`);
`answer_slot_mode` для `compare`. Бой не включать. Проба на стейджинге, когда
свободен.

**Приёмка:** флаг 0 — поведение как до правки; флаг 1 — диагностика двух
вопросов: atom наружу, не refuse/clarify-без-числа.

### Шаг 3 — живой скорер 24

**2 OK класса, 22 не краснеют**, замок гейта §6.2. Выкат на бой — слово
владельца.

### Шаг 4 — граф + документы статуса

Наблюдение в `mcp-memory.json` (этот заход); CHANGELOG / activeContext —
заходом реализации (этот проект их не трогает).

---

## 9. Универсальность

| Проверка девиза | Как проходит |
|---|---|
| Чужая база без правки кода | правило на `proof_status` / `form` / исходе fork, не на именах okna |
| Без ручного разбора вопроса | не списки русских слов; вход — статус атома и slot_mode |
| База-специфика | только в корпусе/`$metadata`/алиасах |
| Если атома нет | refuse/unavailable/clarify как сейчас — защита не снята |

Если реализация чинит «декабрь» или «этот месяц» отдельными ветками под
okna — **брак проекта**, вернуться к §2.1.

---

## 10. Риски (кратко)

1. **Ложный unique** при дыре в E — компенсация §5 + самопроверка §4 контракта
   (метрика недостижимых сущностей).
2. **Показ числа при неверном src** на gate-fail — src уже выбран до compose;
   wrong-entity ловится раньше; этот проект не расширяет trust к focus.
3. **K5b число ≠ gold** после выдачи атома — отдельный хвост compare/окна
   (не K5); класс K5 закрыт исчезновением refuse при computed atom.
