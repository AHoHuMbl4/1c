# Аудит P2

Срез: 10.09.2026. Линза P2: план пакета B v1 — секция **3. B3** + **8. Q1** + замок **B6.3**.
Объект: `docs/audit/FULLB2_PLAN_2026-09-10.md` (v1).
Предшественник: `docs/audit/fullb2-audit-b2.md` (сверка дословно).
Живые якоря: `ubuntu/serenedb/corpus_merge.sql` vec-budget `:864-1162`
(`die_unmatched` `:954-960`, `die_unexplained` `:975-1011`, `xfer` `:923-926`,
гейт loss `:1075-1110`, rehash `:1118-1162`), MERGE-пачки `:1290-1366`,
DELETE `:1371-1374`; мост `corpus_init.sql:129-150`; урок `HOW_NOT_TO.md §3.113`.
Режим: **только чтение**; БД не трогалась, код не менялся, коммитов нет.
Доки SereneDB офлайн недоступны — опора на живой SQL-стиль проекта (CTE,
`error()`, `bridge_row_matches`).

---

## Ответ Q1 (вердикт + SQL)

### Вердикт: **(в)** — два независимых свидетеля; числовой STOP `|expand|≤cap` из old_full / post-mart — нет

| Вариант | Суть | Вердикт |
|---|---|---|
| **(а)** `cap = count(old_full под предком)` (= кандидат-А плана B3.3) | `gone_expand_raw ⊆ {old_full ⋈ bridge(m)}` ⇒ `|expand(m)| ≤ cap(m)` **всегда** | **Само-ссылка.** Cap ничего не режет. Отвергнуть как STOP-порог |
| **(б)** `cap = count(mart под предком) ДО apply` | Единственный нетавтологический числовой cap (R1/1PAR3: COUNT витрины) | Честен, но **запись `fanout_at_apply` при packet_apply — вне окна B** (B = один `corpus_merge.sql`). Post-apply `COUNT(mart)=0` для честного gone → ложный STOP (b2 A2) |
| **(в)** мост ∧ свежий `deleted_gone` ∧ **строки нет в mart**; числовой cap не STOP | Два независимых свидетеля; множество DELETE бюджет не кормит | **Выбор для B.** Режет фальшивку, пока жертвы живы в mart; не тавтология |

**Почему не (а).** План сам строит `gone_expand_raw` из `old_full ⋈ bridge`, затем
`fanout_cap = count(old_full под предком)` и фильтр `|expand|≤cap`. Это сравнение
множества с его же мощностью. Grep-имя `fanout_cap` при такой семантике —
декорация, не R1.

**Почему не post-apply mart COUNT (старый канон 1PAR3 / b2 п.3 без правки).**
После писателей A (persist ⊆ applied) честный `deleted_gone` ⇒ витрина под
предком пуста ⇒ `cap=0` ⇒ любой легитимный expand STOPит. План v1 это уже
замечает («текущая витрина после apply … даёт 0»), но подставляет кандидат-А —
хуже: молчаливый no-op вместо ложного STOP.

**Почему (в) достаточно в скоупе B.** Атака «короткий префикс → тысячи строк»
ломается **пока строки живы в mart**: B3.5(в) `expand-строка жива в mart → STOP`.
Числовой cap нужен как defense-in-depth только когда mart уже пуст, а мост
раздувает множество сверх того, что витрина **когда-либо** держала под этим
`key_text` — это ровно **(б)** и живёт в apply, не в merge.

**Остаточный риск (в) без (б):** маркер-фальшивка на коротком префиксе при
**уже пустой** mart (реальная массовая смерть сущности) — expand «легитимен»
по свидетелю отсутствия; кто стопит раздувание — см. «Атаки» A1. Закрытие —
бэклог (б), не кандидат-А.

### SQL-форма CTE (стиль vec-budget; STOP по cap — нет)

Имена канона B3 сохранить для grep-замка. Семантика `fanout_cap` —
**кардинальность raw для quality / F-фикстур**, не порог STOP.

```sql
-- внутри CREATE … tmp3_merge_vec_budget AS WITH … (рядом с die_*; до MERGE :1290)
gone_markers AS (
  SELECT m.src_table, m.key_text,
         coalesce((SELECT len(k.key_cols) FROM tmp3_key k
                   WHERE k.entity = lower(m.src_table)), 0) AS n_seg
  FROM search_changed_rows m
  WHERE m.op = 'deleted_gone'
    AND epoch(m.ts)::BIGINT
          > coalesce((SELECT v FROM search_quality
                      WHERE k = 'corpus_built_ts' LIMIT 1), 0)::BIGINT
    -- pathology FAIL-closed (стык hash_kill)
    AND m.key_text IS DISTINCT FROM '*'
    AND NOT starts_with(m.key_text, '*|')
    AND NOT starts_with(m.key_text, '*#')
),
gone_expand_raw AS (
  SELECT o.src_table, o.row_key, g.key_text, g.n_seg
  FROM old_full o
  INNER JOIN gone_markers g ON g.src_table = o.src_table
  WHERE g.n_seg > 0
    AND bridge_row_matches(o.row_key, g.key_text, g.n_seg)
    AND o.row_key IS DISTINCT FROM '*'
    AND NOT starts_with(o.row_key, '*|')
    AND NOT starts_with(o.row_key, '*#')
    -- скоуп: только сущности с маркерами (не весь rebuilt без нужды)
    AND o.src_table IN (SELECT DISTINCT src_table FROM gone_markers)
),
fanout_cap AS (
  -- НЕ порог STOP. Кардинальность raw per-marker → search_quality / замки.
  -- Числовой STOP |expand|≤cap — только после (б) persist fanout_at_apply.
  SELECT src_table, key_text, count(*)::BIGINT AS cap
  FROM gone_expand_raw
  GROUP BY 1, 2
),
gone_expand AS (
  SELECT r.src_table, r.row_key
  FROM gone_expand_raw r
  WHERE EXISTS (
    SELECT 1 FROM gone_markers g
    WHERE g.src_table = r.src_table AND g.key_text = r.key_text
  )
  -- свидетель витрины: строки НЕТ в mart (независим от DELETE-множества)
  -- форма NOT EXISTS — через query_table / тот же мир, что deleted_delta_rows;
  -- точный предикат ключа витрины (Ref_Key / Recorder|Line) — по key_cols сущности
  AND NOT EXISTS (
    SELECT 1 /* mart-alive(r) — row-level; само-объяснение запрещено */
  )
)
```

Отдельные `SELECT CASE … error()` (B3.5): (а) строка в кандидате expand без
предка-маркера; (в) expand-строка жива в mart. Пункт (б) `|expand|>cap` из
плана v1 — **снять** до появления persist (б); иначе либо мёртвый код
(кандидат-А), либо ложный STOP (post-mart).

План B3.3/B3.4/B3.5(б) и Q1 в текущей редакции — **противоречие**: закрыть
правкой плана до кода.

---

## Формула EXCEPT

Живое: `die_unexplained` уже **COUNT с фильтрами** (`:975-1011`); колонка
`векторов_умрёт` = `coalesce(du.n)` в финальном SELECT `:1047`; в
`search_quality` уходит `sum(векторов_умрёт)` как `vector_loss_gate`
(`:1075-1082`), гейт `error()` — `:1084-1110`. Имени `unexpected` нет
(b2 пробел №1) — план B3.6 верно закрепляет алиас.

`xfer` CTE `:923-926` считает только `векторов_спасено_картой` по **новым**
ключам `tmp3_merge_emb_xfer`; из `векторов_умрёт` **не** вычитается (b2).
Карта xfer = новые `row_key`; для EXCEPT нужны **старые** unmatched-ключи,
чей контент уехал на новый ключ.

### CTE-цепочка (в стиле файла; множества, не арифметика COUNT)

```sql
-- 1) unmatched с emb (row-level; ядро die_unmatched без GROUP BY)
unmatched_emb_rows AS (
  SELECT o.src_table, o.row_key, o.ch, o.bmap, o.refs /* если есть в old_full */
  FROM old_full o
  WHERE o.emb IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM new_full n
      WHERE n.src_table = o.src_table AND n.row_key = o.row_key)
),
-- 2) текущие entity-свидетели + ch-баланс → row-level (как сейчас :975-1011,
--    но SELECT src_table, row_key без count)
die_unexplained_base AS (
  SELECT u.src_table, u.row_key
  FROM unmatched_emb_rows u
  WHERE /* NOT EXISTS ch-баланс — тот же предикат, что :988-996 */
        /* NOT EXISTS key_deleted_delta / collapse / rewrite / shrink / repost —
           при mode=partial key_deleted_delta → замена на gone_expand (B2.2);
           при mode=full — как сейчас; слепо не выкидывать (b2 пробел №4) */
),
-- 3) старые ключи, объяснённые картой xfer (контент на новом row_key)
xfer_old_keys AS (
  SELECT u.src_table, u.row_key
  FROM unmatched_emb_rows u
  WHERE EXISTS (
    SELECT 1
    FROM tmp3_merge_emb_xfer x
    INNER JOIN new_full n
            ON n.src_table = x.src_table AND n.row_key = x.row_key
    WHERE n.src_table = u.src_table
      AND n.ch IS NOT DISTINCT FROM u.ch
    -- узкий мир: только rewrite_wave сущности (как emb_old :805-816);
    -- refs+bmap-ветка — OR с corpus_bmap_common_eq по образцу :850-853
  )
),
-- 4) МНОЖЕСТВЕННАЯ разность (запрет count−count−count)
die_unexplained_new AS (
  SELECT src_table, row_key FROM die_unexplained_base
  EXCEPT
  SELECT src_table, row_key FROM gone_expand
  EXCEPT
  SELECT src_table, row_key FROM xfer_old_keys
),
die_unexplained AS (
  SELECT src_table, count(*)::BIGINT AS n
  FROM die_unexplained_new
  GROUP BY 1
)
```

`EXCEPT` двуместный; цепочка из двух EXCEPT = `(base \ gone) \ xfer`.
Пересечение `gone_expand ∩ xfer_old_keys` вычитается один раз — двойного
зачёта нет (атака A3). Приоритет классов для quality-причины можно писать
отдельно; на мощность `n` не влияет.

### Где пересчитывается `векторов_умрёт` и что в quality

| Точка | Что |
|---|---|
| Финальный SELECT vec-budget `:1040-1073` | `coalesce(du.n, 0) AS векторов_умрёт` — **единственное** место колонки; после правки `du` ← `die_unexplained` над `die_unexplained_new` |
| `INSERT search_quality` `:1075-1082` | `k='vector_loss_gate'`, `v=sum(векторов_умрёт)` |
| `SELECT CASE error()` `:1084-1110` | порог `sum(векторов_умрёт)/emb_total > tol` |
| `причина` `:1049-1066` | текст для quality/error; при `du.n=0` и `unmatched>0` — «объяснён …»; после B3 добавить ветку/алиас `unexpected≡векторов_умрёт` в комментарии/quality detail |
| Rehash `:1118-1162` | **не** трогать; `hash_kill_unexplained` ортогонален (§3.113) |

При `partial_rebuild=0` тела B3 мертвы (B3.7) — горячий путь `die_unexplained`
байт-семантика ≡ текущей (доказывается B7, не декларацией).

**Дыра плана:** SQL-форма `xfer_old_keys` не специфицирована (только словами).
Без неё исполнитель вычтет новые ключи xfer или сделает COUNT — регресс A3.
Зафиксировать CTE выше в плане до кода.

---

## Атаки

### A1. Маркер-фальшивка на коротком префиксе + реальная массовая смерть (mart пуст)

**Как.** Свежий `deleted_gone` с коротким `key_text`; ветка 3 моста
(`len(split)<n_seg` → `starts_with(row_key, marker||'|')`, `corpus_init.sql:144-147`)
раздувает expand на тысячи строк ТЧ/движений. Сущность реально вычищена из
витрины → свидетель «нет в mart» истинен для всего expand.

**Легитимен ли expand?** По букве (в) — да: предок есть, строк в mart нет.
**Кто стопит?** Числовой cap из (а) — никто (тавтология). Cap из post-mart —
ложный STOP и на честном маркере. **Стопит только (б)** (`fanout_at_apply` под
тем же `key_text`: `|raw| > persist_cap → error`), либо транспорт-гейт
«короткий/неполный маркер» (сейчас в B3 нет).

**В план:** явно описать A1 как остаточный риск (в); либо мини-шаг apply (б)
вне «только merge», либо доп. STOP «маркер короче declared object key»
(осторожно с fold/n_seg=1). F1 замка переписать под это, не под K%.

### A2. Двойное вычитание `gone ∩ xfer`

**Как.** `count(unmatched)−count(gone)−count(xfer)` при пересечении занижает
`векторов_умрёт` (b2 A3). Реально при широком маркере + rewrite/ch-карте.

**Защита.** `EXCEPT`-цепочка выше; замок: модель
`|base| − |base∩gone| − |base∩xfer∩¬gone| = |die_unexplained_new|`, не сумма
двух COUNT. План B3.6 / B6.3 это заявляет — **достаточно**, если SQL
`xfer_old_keys` зафиксирован.

### A3. Gone-маркер старый (`ts ≤ corpus_built_ts`) на живой строке

**Как.** Исторический `deleted_gone` остаётся в `search_changed_rows`; без
окна свежести объясняет новый wipe / hash-мир.

**Защита в плане:** B3.1 `epoch(ts) > corpus_built_ts` — **внесено** (b2
пробел №11). Дополнить замком: маркер со старым ts ∉ `gone_markers` ⇒ не в
expand, не уменьшает unexplained; живая строка в mart при «старом gone» не
даёт PASS.

### A4. Патология `*` минует мост (n_seg>1, ветка 3)

**Как.** `key_text='*'` / корпусный `*|…`: `bridge_row_matches('*|1','*',2)`
истинно (hash_kill lock:211-218). Сентинель как предок → объектная ветка
матчит почти всё.

**Защита в плане:** B3.2 pathology → пусто — **внесено**. Проверить, что
фильтр на **обоих**: маркер и `row_key` корпуса; иначе `*` только в корпусе
при нормальном маркере всё ещё протечёт в raw. Замок F6 — оставить.

### A5. Потеря производительности — expand по всему `old_full` каждый такт

**Урок:** FULLB_PLAN этап 1c `:182-183` — hash anti-join / reuse vec-budget,
не второй полный проход; b4 атака 5 ссылается на «урок :866, 21 ГиБ tmp».
`old_full` уже сканирует корпус rebuilt (`:894-900`). Добавить
`gone_expand_raw` = `old_full ⋈ markers` без скоупа → ещё один тяжёлый join
на каждом полном merge; при `partial_rebuild=0` тела мертвы (B3.7), но при
первом partial — риск.

**Где ограничить скоуп:**
1. `o.src_table IN (SELECT DISTINCT src_table FROM gone_markers)` — обязательно;
2. не строить expand при `gone_markers` пуст (короткое замыкание CTE/ветки);
3. не второй проход корпуса вне уже материализованного `old_full` (reuse);
4. запрет коррелированного `EXISTS` по всему `search_corpus` вне `old_full`;
5. приёмка B7: пик `.tmp` / wall merge ≤ базовой линии (в плане есть) —
   явно привязать к expand-CTE.

**В v1 B3 скоуп производительности не записан — упущение.**

### A6 (бонус). Само-объяснение DELETE≡expand

Покрыто B3.4 (свидетель mart) + B3.5 + F5. При A1 (mart пуст) само-объяснение
частично возвращается: DELETE и budget кормятся одним фактом «нет в mart».
Это принятый остаток (в), не дыра кандидата-А.

---

## Замок

Файл: `test_merge_gone_expand_lock.py` (B6.3). Источник веток — b2 F1–F7.

| Ветка | Смысл b2 | Достаточна ли при Q1=(в)? |
|---|---|---|
| F1 | expand > fanout → STOP | **Переписать:** убрать K%/COUNT(mart) как PASS-критерий; сценарий A1 (короткий префикс + mart∅) → ожидание «без (б) — PASS по (в) / с persist — STOP» явно |
| F2 | expand без предка → STOP | Да |
| F3 | PASS только при fanout=COUNT(mart) | **Устарела** относительно (в) и post-apply; противоречит B3.3 кандидат-А. Заменить: PASS при мост∧¬mart∧свежий маркер; FAIL при живой mart-строке в expand |
| F4 | grep unexpected/gone_expand без cap | Да, но имена — **дословно** канон плана |
| F5 | само-объяснение FAIL | Да |
| F6 | pathology `*` | Да |
| F7 | n_seg=0 → пусто | Да |

**F1–F7 недостаточны без правок F1/F3 и дополнений.** Добавить:

| + | Что |
|---|---|
| **G0** | grep **дословно** CTE: `gone_markers`, `gone_expand_raw`, `fanout_cap`, `gone_expand` — все четыре в `corpus_merge.sql`; отсутствие любого при наличии вычитания expand → FAIL |
| **F8** | stale ts: `epoch(ts) ≤ corpus_built_ts` → не в `gone_markers` |
| **F9** | EXCEPT: фикстура `gone∩xfer ≠ ∅` → `|unexpected|` = множественная разность, не `a−b−c` по COUNT; запрет трёх независимых `count(*)` в формуле `векторов_умрёт` |
| **F10** | скоуп: при пустых `gone_markers` нет join-паттерна expand ко всему корпусу; grep/модель «src_table IN (gone_markers)» |
| **F11** | mode=full / `partial_rebuild=0`: вычитания gone_expand нет (B3.7 / §9.7) |
| **F12** | error() cap/⊆ (или ⊆-only) **выше по тексту**, чем `DELETE FROM search_corpus` и чем первый MERGE-пачки |

Текст B6.3 «PASS только при fanout=COUNT» — **синхронизировать с вердиктом Q1**
до реализации замка, иначе замок закрепит отвергнутую семантику.

---

## Внесено/упущено из b2

Сверка 12 пробелов + 6 атак + вердикт-условия P1–P5 / «внедрять только если».

### Пробелы b2 → v1

| # | Пробел b2 | В v1? |
|---|---|---|
| 1 | Имя `unexpected` vs `векторов_умрёт` | **Да** — B3.6 алиас |
| 2 | `gone_expand` отсутствует | **Да** — B3 целиком |
| 3 | xfer не вычитается | **Да** — B3.6 EXCEPT (SQL `xfer_old_keys` не дописан) |
| 4 | entity-свидетели vs row-level; не слепо удалять NOT EXISTS | **Частично** — B2.2 замена на gone_expand при partial; нет явного «full оставить / доказать покрытие» |
| 5 | порядок 1a↔1c | **Да** — атомарность B7; запрет 1c≺1a |
| 6 | repost `starts_with` | **Да** — B4 (сосед) |
| 7 | K% vs R8 | **Да** — §9.3 вычеркнут |
| 8 | канон имён CTE для grep | **Да** — B3 шапка имён |
| 9 | EXCEPT vs COUNT | **Да** — B3.6 |
| 10 | расширять vector_budget lock, не только hash_kill | **Частично** — новый `test_merge_gone_expand_lock.py`; `test_vector_budget_gate.py` не упомянут |
| 11 | окно ts = rehash | **Да** — B3.1 |
| 12 | не учить rehash `op=full` | **Да** — §9.2 |

### Атаки b2 → v1

| # | Атака | Внесено? |
|---|---|---|
| A1 | фальшивка + fanout | **Сломано кандидатом-А** (cap no-op); mart-свидетель есть; A1 при mart∅ не разобран |
| A2 | fanout=0 после apply | **Замечено** в B3.3/Q1, но ответ = кандидат-А (хуже) |
| A3 | двойное вычитание | **Да** — EXCEPT |
| A4 | pathology `*` | **Да** — B3.2 |
| A5 | само-объяснение | **Да** — B3.4–5 + F5 |
| A6 | n_seg=0 | **Да** — B3.2 |

### Условия «внедрять 1c» (b2 вердикт) → v1

| # | Условие | В v1? |
|---|---|---|
| 1 | cap = COUNT(mart), не константа | **Нет / подмена** на old_full (само-ссылка). R8 «не константа» соблюдён буквой, смысл R1 — нет |
| 2 | deleted_gone ∧ cap ∧ свидетель (AND) | **Частично** — AND есть, но cap из (а) пустой |
| 3 | error() до DELETE | **Да** — B3 место + B3.5 |
| 4 | запрет само-объяснения + F1–F7 + grep | **Да** с оговоркой F1/F3 |
| 5 | разность множеств | **Да** |
| 6 | n_seg=0 / `*` → запрет | **Да** |
| 7 | не трогать rehash/full | **Да** |

### Список упущенного (конкретно)

1. **Q1 не закрыт:** кандидат-А оставлен в B3.3 при открытом Q1 → внутреннее противоречие с R1.
2. **SQL `xfer_old_keys`** (проекция старых ключей) не задан.
3. **Скоуп/perf expand** (reuse old_full, только src с маркерами, запрет второго скана) — нет в B3; есть урок FULLB `:182-183` / b4.
4. **A1 при пустой mart** — нет явной нормы «кто стопит».
5. **B6.3 / F3** всё ещё «fanout=COUNT(mart)» при B3.3 = old_full.
6. **`test_vector_budget_gate.py`** не в списке B6 (b2 пробел №10).
7. **Пробел №4:** правило «не удалять entity-NOT EXISTS у mode=full без доказательства» — не дописано.
8. **P2 paths b2:** sources-orphan DELETE без vec-budget — вне B3, ок; не регрессия плана.

---

## Вердикт

**План B3 v1 почти собирает R1-комплект по именам и замкам, но спотыкается
на источнике `fanout_cap`.**

1. **Q1 = (в).** Кандидат-А (а) — само-ссылка, как STOP отвергнуть. Post-apply
   mart COUNT ломает честный gone. Числовой cap — только (б) вне окна merge;
   в B — пара свидетелей мост+¬mart; `|expand|≤cap` из B3.5(б) снять или
   отложить.
2. **EXCEPT-формула** ясна; нужно дописать CTE `xfer_old_keys` и row-level
   `die_unexplained_*` до кода — иначе риск снова скатиться в COUNT.
3. **Замок F1–F7** недостаточен без G0 (дословные имена CTE) + F8–F12 и
   правки F1/F3 под (в).
4. **Из b2:** 9/12 пробелов внесены, 2 частично, ядро A1/cap — **упущено /
   ухудшено** кандидатом-А; 5/6 атак закрыты текстом, A1 при mart∅ — нет.

**К показу владельцу / к коду B3:** НЕ ГОТОВ, пока в плане не зафиксированы
вердикт Q1=(в), правка B3.3–B3.5, SQL `xfer_old_keys`, скоуп expand, обновление
B6.3. После этих правок текста — можно второй проход замков и реализация в
`corpus_merge.sql` одним md5 с B1/B2.

Статус аудита P2: **план B3 требует правки Q1+замка; код не трогался.**
