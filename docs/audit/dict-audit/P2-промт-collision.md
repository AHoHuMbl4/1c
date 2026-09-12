# P2 — коллизионный промт v2 (разведение одного слова)

Дата: 13.09.2026 (cursor, read-only).  
База аудита: `00-СВОДКА.md`, `B5-промты.md`, `A2-синонимы.md`; код: `wiki_alias.sh:276–362`, `:312`, `wiki_alias_collision_round.sql`, `wiki_alias_collision_left.sql`, `wiki_alias_collision_merge.sql`.  
Коммитов нет. Ниже — дословный английский промт + правила сходимости по-русски.

---

## Вердикт

Старый промт (`:312`) **намеренно** оставляет общее слово в aliases (верно: замер okna 25.08, «клиент» → пусто без него), но **не просит** различителей в aliases и сводит `notEnoughFor` к именам соседей. Итог аудита: 333 слова-коллизии, ~96% NEF = «разведение соседей», thematic «не я» отсутствует, 13 живых столкновений не доспросили. v2 сохраняет общее слово, **добавляет 1–2 различителя** и требует в NEF **тему**, которую человек под этим словом скорее ищет у соседа.

---

## 1. Дефект текущего промта (коротко)

| Что есть | Чем плохо |
|---|---|
| «everyday words that also fit siblings **stay** in aliases» | Коллизия по индексу живёт вечно — ок для recall, но без различителей меню/судья не отличают |
| «sibling distinction goes in notEnoughFor» + «the other **types** … and what each answers» | NEF = имена соседей, не темы (B5 §3.1, A4) |
| Нет few-shot | Модель копирует init-паттерн «навалить aliases» |
| В Input **нет** самого shared word (`collision_round` отдаёт entity/title/quantities; `WORD` в msg не кладётся) | Модель **угадывает**, какое слово общее |
| Collision MERGE — **полная перезапись** трёх полей (B1) | Без «keep shared + add 1–2» легко снести роль-слова первого прохода |

---

## 2. Цель раунда (критерий «разведено»)

После одного успешного ответа модели по слову W у **каждой** сущности пачки:

1. **aliases** содержат W (запрет выкидывать).
2. **aliases** содержат **1–2 различительных** обиходных слова/фразы (1–3 слова каждое), по которым набор сущности ≠ набору соседа *или* пересечение осмысленно (одна роль в разных потоках — допустимо; пустой контраст — нет).
3. **notEnoughFor** называет **темы-конкуренты** («остатки на складе», «текущий прайс», «список покупателей»), а не только machine/title соседа; сосед можно упомянуть вторым членом («… → см. &lt;title из Input&gt;»).
4. Никаких слов вне Input (title / quantities / явно переданное shared word) и никаких мета-ярлыков платформы.

«Сведено» для SQL-кандидата (`collision_left`) по-прежнему: в `not_enough_for` есть упоминание W **или** probe на (W, fp). v2 не меняет эту механику — меняет **качество** того, что пишется.

---

## 3. Дословный промт v2 (английский)

Подстановка перед Input (обязательная проводка кода — сейчас отсутствует):

- `<SHARED_WORD>` — слово из `ROUND` (`WORD`), lower/trim как в SQL.
- Рекомендуемое расширение Input (не в этой задаче править SQL, но промт на него рассчитан): к каждому item добавить `"aliases":"<текущая CSV-строка>"`, иначе модель заново собирает aliases и MERGE затирает роли первого прохода.

**Текст целиком (одна строка для `printf`, здесь с переносами для чтения; в коде — без `\n` между предложениями, как сейчас, либо одна строка):**

```
JSON only, no prose, no code fences. The record types in Input are ALL CALLED BY THE SAME WORD in this database. That shared word is "<SHARED_WORD>": a person who types only that word could mean any type below. For EACH type, in the SAME language as its title, rebuild the three fields as follows.

(1) aliases — MUST keep "<SHARED_WORD>" in the list (never drop it: people use it). Also keep the title if it is already an everyday asking-word; do not invent case/number variants of the same stem. ADD exactly 1 or 2 DISTINCTIVE everyday words or short phrases (1-3 words each) that a person would use when they mean THIS type and not the siblings — grounded only in this type's title and quantities from Input (and in its current aliases if Input lists them). Distinctive phrases may stay unique to this type, or overlap a sibling only when both truly share that role; empty contrast (only the shared word and bare title for every sibling) is forbidden. Do not add platform meta-labels (list, catalog, register, journal, document, types, kinds, directory, registry). Do not add Latin tokens when the title is not Latin. If unsure a word is everyday for THIS type — omit it.

(2) bestUsedFor — 2 to 4 short topic templates this type alone answers among the siblings (not full sentences, no foreign topics that belong to a sibling).

(3) notEnoughFor — when a person says "<SHARED_WORD>" but means a COMPETITOR TOPIC that another type in this list answers better, name that TOPIC (what they are looking for), then optionally the sibling title from Input. Prefer themes over bare sibling names. Example shape: "stock on hand / warehouse balances — see <sibling title>"; "current price list — see <sibling title>". Do not invent siblings outside Input. If unsure — omit that line.

Few-shot (English scaffold only; YOUR output language = language of each title): Shared word "party". Types: {title:"Business partners", quantities:"headcount"} and {title:"Legal counterparties", quantities:"taxpayer id"}. Good items sketch: partners aliases ["party","partners","buyers"] bestUsedFor ["who we sell to","partner headcount"] notEnoughFor ["legal taxpayer / contract party — see Legal counterparties"]; counterparties aliases ["party","counterparties","legal entities"] bestUsedFor ["taxpayer id","contract party"] notEnoughFor ["sales partner list — see Business partners"]. Bad: dropping "party"; aliases that are only ["party"] for both; notEnoughFor that only repeats the other type's machine id with no topic.

Schema: {"items":[{"entity":"...","aliases":["..."],"bestUsedFor":["..."],"notEnoughFor":["..."]}]}. Every Input entity must appear once; entity values copy Input exactly. Input: 
```

После двоеточия — JSON пачки как сейчас (`cat "$TMP/pay"`).

---

## 4. Таблица: дыра старого → закрытие в v2

| Недостаток (B5 / сводка) | Как закрыт |
|---|---|
| Нет различителей в aliases | «ADD exactly 1 or 2 DISTINCTIVE…»; empty contrast forbidden |
| Запрет снимать общее слово (нужен!) был, но без контраста | «MUST keep SHARED_WORD»; few-shot Bad: dropping |
| NEF ≈ имена соседей | «name that TOPIC… Prefer themes over bare sibling names» |
| Нет thematic «не я» | Форма «stock on hand… / current price list…» в инструкции + few-shot |
| Нет few-shot | Один EN-каркас party/partners/counterparties |
| Слова не из базы / мета | «grounded only in … Input»; запрет meta-labels; «If unsure — omit» |
| Shared word не в msg | Явный слот `<SHARED_WORD>` (нужна правка оболочки) |
| Полная перезапись ролей | Промт: current aliases if listed; отдельно — расширить Input aliases (код) |

---

## 5. Правила сходимости

### 5.1. Сколько раундов разумно

| Уровень | Правило |
|---|---|
| **На одно слово W** | **Ровно один успешный** ответ модели на набор сущностей с данным `fp`. Повтор того же (W, fp) не нужен: probe уже стоит до вызова; SQL убирает слово из `cand`, когда у носителей в `not_enough_for` есть W. |
| **На такт** | Дефолт `WIKI_ALIAS_COLLISION_ROUNDS=40` — потолок **слов за такт**, не «итераций улучшения». При ~333 поверхностных коллизиях (A2) полный первый обход ≈ **9 тактов** по 40, либо поднять ROUNDS/бюджет на песочнице. |
| **Сходимость качества** | После одного хорошего JSON наборы должны быть различимы по п.2. Второй проход по тому же W имеет смысл только если сменился `fp` (новая сущность с тем же словом) или force-сброс probe. |
| **Пачка > BATCH** | Сейчас `LIMIT :batch` режет сущности, а `fp`/probe — по **всем** носителям (`collision_round.sql`). Риск: спросили 20 из 32, слово «закрыто». Для слов с n≫BATCH — либо поднять batch на collision, либо крутить по подмножествам с отдельным fp (код вне этой задачи). Пока: на песочнице для топа коллизий (`тмц`×32 и т.п.) batch ≥ n. |

Практическая рекомендация песочницы (`alias_okna_c5`): **ROUNDS=60–80** на один длинный прогон force-словаря + проверка `collision_left → 0` и выборочный ручной разбор топ-слов (A2). Не гонять десятки кругов на одно слово — probe это запрещает, а MERGE всё равно затрёт тем же уровнем шума.

### 5.2. Когда считать слово «сведённым»

1. Модель вернула `items` на всех entity пачки.
2. У каждого item: `"<SHARED_WORD>"` ∈ aliases (после parse/normalize).
3. У каждого item: ≥1 различитель помимо shared (+ title, если он уже был обиходным).
4. У каждого item: ≥1 строка notEnoughFor с **темой** (не только чужой `src_table`).
5. SQL: `not_enough_for ILIKE '%'||W||'%'` — чтобы `collision_left` не тащил слово снова (сейчас критерий кандидата именно такой — поэтому в NEF **должно** фигурировать само W или его тема-контекст; безопаснее явно включать shared word в текст NEF, напр. `"\"client\" as warehouse topic — see …"` / на языке title: тема + слово).

Рекомендация к формулировке NEF (дополнение к промту, если на живом прогоне SQL снова ловит слово): одна из строк notEnoughFor должна содержать само `<SHARED_WORD>`, иначе `cand` не очистится. Добавить в конец п.(3) одну фразу:

> At least one notEnoughFor entry per type must include the shared word "<SHARED_WORD>" so later passes can see the collision was addressed.

(В блок выше уже заложено «when a person says SHARED_WORD» — модель часто повторит слово; если замер покажет иначе — включить эту фразу явно в printf.)

### 5.3. Финальные неразведённые

Остаток после исчерпания ROUNDS/бюджета / осечки JSON (`разведено сущностей: 0` при уже проставленном probe):

| Ситуация | Действие |
|---|---|
| Слово в `collision_left` (probe не стоял) | Следующий такт спросит сам — ничего не выкидывать из aliases |
| Probe стоит, поля пустые/старые (осечка модели) | **Не снимать** общее слово вручную. Различители не выдумывать кодом. Варианты: сменить fp (редко) или force: удалить строку probe для (alias, fp) и переспросить; либо точечно `WIKI_ALIAS_WORD=<слово>` |
| Модель ответила, но контраст слабый (только shared+title) | Считать **не сведённым по качеству**; общий слово **оставить**; различители — из title/quantities повторным force-раундом, не удалением shared |
| n сущностей делят W навсегда (истинный омоним речи) | Это **норма**: shared остаётся у всех; различители + thematic NEF — достаточный финал. Индекс по-прежнему вернёт нескольких кандидатов → меню/verify (контракт «один путь»), не «вычистить коллизию из aliases» |

**Запрет на «сведение» выкидыванием общего слова** — жёсткий (okna 25.08). Финал всегда: `shared ∈ aliases` + различители + тематический NEF; уникальность всего словаря aliases **не** цель коллизионного круга.

---

## 6. Риски для Qwen3.8-27B

| Риск | Митигация |
|---|---|
| Выкинет SHARED_WORD «чтобы развести» | MUST keep + Bad few-shot; пост-проверка кодом (если нет слова — reject merge / retry) желательна |
| NEF снова только имена | «Prefer themes»; few-shot с «legal taxpayer / contract party» |
| Различители = падежи title | «do not invent case/number variants» |
| Мета list/catalog | явный запрет (согласовано с P1/P3) |
| Затрёт роли первого прохода | расширить Input aliases; иначе промт просит rebuild «grounded in title/quantities» — роли из flows в collision Input сейчас **нет** |
| Не повторит W в NEF → слово снова в cand | явная фраза §5.2 или код: при merge дописывать W в nef, если модель забыла |
| Англ. few-shot утечёт в RU-aliases | «YOUR output language = language of each title» (как в init) |

---

## 7. Совместимость со схемой и соседями задач

- JSON-схема **та же** (`items[].entity|aliases|bestUsedFor|notEnoughFor`) — parse/MERGE без смены контракта.
- P1 (init) запрещает слова соседей в aliases; **P2 наоборот** оставляет shared у всех — это разные фазы, не противоречие: init минимизирует кашу, collision чинит уже случившуюся кашу без потери recall.
- P3 (фильтр мета-слов) не должен вырезать SHARED_WORD и различители, если они не из стоп-словаря платформы.
- Наблюдаемость (сводка §6): счётчик «коллизий сведено» = слова, ушедшие из `collision_left` за такт + доля пачек с ≥1 различителем на entity (проверка после parse).

---

## 8. Готовый однострочник для вставки в `wiki_alias.sh` (после подстановки WORD)

Ниже — тот же текст в одну логическую строку (для копирования в `printf '%s'`). Перед ним в оболочке: подставить слово в шаблон.

```
JSON only, no prose, no code fences. The record types in Input are ALL CALLED BY THE SAME WORD in this database. That shared word is "<SHARED_WORD>": a person who types only that word could mean any type below. For EACH type, in the SAME language as its title, rebuild the three fields as follows. (1) aliases — MUST keep "<SHARED_WORD>" in the list (never drop it: people use it). Also keep the title if it is already an everyday asking-word; do not invent case/number variants of the same stem. ADD exactly 1 or 2 DISTINCTIVE everyday words or short phrases (1-3 words each) that a person would use when they mean THIS type and not the siblings — grounded only in this type's title and quantities from Input (and in its current aliases if Input lists them). Distinctive phrases may stay unique to this type, or overlap a sibling only when both truly share that role; empty contrast (only the shared word and bare title for every sibling) is forbidden. Do not add platform meta-labels (list, catalog, register, journal, document, types, kinds, directory, registry). Do not add Latin tokens when the title is not Latin. If unsure a word is everyday for THIS type — omit it. (2) bestUsedFor — 2 to 4 short topic templates this type alone answers among the siblings (not full sentences, no foreign topics that belong to a sibling). (3) notEnoughFor — when a person says "<SHARED_WORD>" but means a COMPETITOR TOPIC that another type in this list answers better, name that TOPIC (what they are looking for), then optionally the sibling title from Input. Prefer themes over bare sibling names. Example shape: "stock on hand / warehouse balances — see <sibling title>"; "current price list — see <sibling title>". Do not invent siblings outside Input. If unsure — omit that line. At least one notEnoughFor entry per type must include the shared word "<SHARED_WORD>" so later passes can see the collision was addressed. Few-shot (English scaffold only; YOUR output language = language of each title): Shared word "party". Types: {title:"Business partners", quantities:"headcount"} and {title:"Legal counterparties", quantities:"taxpayer id"}. Good items sketch: partners aliases ["party","partners","buyers"] bestUsedFor ["who we sell to","partner headcount"] notEnoughFor ["legal taxpayer / contract party — see Legal counterparties"]; counterparties aliases ["party","counterparties","legal entities"] bestUsedFor ["taxpayer id","contract party"] notEnoughFor ["sales partner list — see Business partners"]. Bad: dropping "party"; aliases that are only ["party"] for both; notEnoughFor that only repeats the other type's machine id with no topic. Schema: {"items":[{"entity":"...","aliases":["..."],"bestUsedFor":["..."],"notEnoughFor":["..."]}]}. Every Input entity must appear once; entity values copy Input exactly. Input: 
```

Проводка оболочки (не сделана в этой задаче):

```bash
# было: фиксированная строка без WORD
# нужно: SHARED="$WORD" и sed/printf с подстановкой в шаблон выше, затем cat pay
```

---

## Источники

- `ubuntu/serenedb/wiki_alias.sh:276–362`, `:310–312`
- `ubuntu/serenedb/wiki_alias_collision_{round,left,merge}.sql`
- `docs/audit/dict-audit/{00-СВОДКА,B5-промты,A2-синонимы,A4-объяснения,B1-конвейер-полей,A5-модель}.md`
- Замер okna 25.08 (не выкидывать обиходное общее слово) — комментарий `:310–311`
