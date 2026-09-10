# Аудит P1

Линза: B1/B2 (ветвление DELETE + гварды). Режим: только чтение.
Дата: 10.09.2026. Объект: `docs/audit/FULLB2_PLAN_2026-09-10.md` v1
(секции «ФАКТ ПРОДА», «1. B1», «2. B2», «7. B7»).
Предшественник: `docs/audit/fullb2-audit-b1.md`.
Живой код: `ubuntu/serenedb/corpus_merge.sql` (1497 строк),
`ubuntu/serenedb/test_changed_rows_lock.py:131-133`.

**Краткий вердикт:** якоря шапки сверены с кодом (все совпали). `\if` вокруг
DELETE синтаксически верен для psql stdin (0/1). Ответы Q2–Q5 ниже — конкретные
предикаты; **в v1 их ещё нет**, план оставляет их открытыми. P1-часть **не готова**
к выкату/детализации SQL без дословных правок: (а) parent/child «закрыт» декларацией
без механизма удаления детей; (б) гвард `ent_guard` 0.1% (`:637-653`) не в B2;
(в) `die_unmatched` (`:954-960`) не сужен при том, что B2.2 трогает только
`die_unexplained`; (г) сужение unmatched без изоляции full-сущностей ломает
shrink/repost-свидетелей в mixed-такте.

---

## Сверка якорей

| Якорь плана (шапка / B1–B2) | Код | Вердикт |
|---|---|---|
| anti-join DELETE **:1371-1374** | `DELETE FROM search_corpus c WHERE … IN (tmp3_corpus) AND NOT EXISTS (tmp3…row_key)` | **ок** |
| sources-orphan **:1381-1382** | `DELETE … WHERE NOT EXISTS (search_sources…)` | **ок**, вне ветвления |
| empty-build **:117-121** | `tmp3_build` без строк в `tmp3_corpus` → `error(…пустыми…)` | **ок** |
| сторож A **:123-130** | `:partial_rebuild = 0 AND mode IS DISTINCT FROM 'full'` | **ок** |
| rewrite-wave **:209-214** | `было>0 AND стало>=было AND (было-matched)/было≥0.9 AND \|Δ\|/было≤0.05` | **ок** |
| unmatched **:223-333** | каркас + `p_merge_unmatched` / `_period` + `\gexec` | **ок** |
| orphan `deleted_delta_rows` **:577-582** | orphan_rec × ¬doc_alive | **ок** (витрина, не маркеры) |
| JOIN `key_deleted_delta` **:620-625** | collapse_cand ⋈ deleted_delta_rows | **ок** |
| гвард 10% **:688-709** | `уйдёт / count(search_corpus) > 0.1` минус form/wave/collapse/deleted/shrink/repost | **ок** |
| die_unmatched **:954-960** | emb≠NULL ∧ ∉ new_full | **ок** |
| die_unexplained **:975-1011** | unmatched минус ch-баланс / deleted_delta / collapse / wave / shrink / repost | **ок** |
| count-equivalence **:1470-1478** | `в_корпусе <> собрано` по `tmp3_corpus` | **ок** |
| замок `\if` **test_changed_rows_lock.py:131-133** | assert `"\\if :partial_rebuild" not in build/merge` | **ок** (конфликт с B1.1 — план B1.3 снимает) |
| `\set partial_rebuild 0` | merge:4-6 | **ок** |
| MERGE-пачки **:1290-1366** / emb_xfer **:1393-1399** / vec-budget **:864-1162** | совпадают | **ок** (вне P1-правок, шапка верна) |

### `\if` / `\else` / `\endif` + `ON_ERROR_STOP`

План B1.1: `\if :partial_rebuild` … `\else` … `\endif` вокруг DELETE-зоны.

1. **Синтаксис psql.** Метакоманды клиента; в false-ветке SQL **не уходит** на
   сервер. Образец в дереве: `embed_missing.sql:22-28` (`\if :use_rows_filter`),
   `resolver_build.sql:58`. Значения `0`/`1` — валидные boolean для `\if`
   (docs psql; живой урок CHANGELOG 29.08: `\if` **не** принимает произвольное
   число вроде 1645731 — только 0/1/on/off/…). Для `:partial_rebuild` ∈ {0,1}
   — **исполнимо дословно**.

2. **Семантика ветки.** `\set partial_rebuild 0` → `\if 0` = false → выполняется
   `\else` = текущий anti-join :1371-1374. `=1` → true → partial-тело.
   Else «байт-в-байт» достижим, если в `\else` лежит **дословная** копия
   :1371-1374 без правок (как пишет B1.1).

3. **`ON_ERROR_STOP` (файл:2 = on).**
   - Ошибка SQL в **активной** ветке → psql рвёт скрипт (код 3); незакрытый
     BEGIN пачки откатывается (комментарий :1291-1294) — поведение не меняется
     от появления `\if`.
   - SQL в **неактивной** ветке на сервер не шлётся → `ON_ERROR_STOP` его не
     видит (в т.ч. синтаксический мусор в мёртвой ветке **не** стопит — риск
     только для человека/замка, не для hot path).
   - Невалидное выражение `\if` (не boolean) при `ON_ERROR_STOP on` стопит
     клиент и ломает pairing веток — поэтому держать только 0/1 и не подставлять
     счётчики (урок embed_missing).
   - Внутри файла есть локальные `\set ON_ERROR_STOP off` (:546-550, :565-570)
     вокруг INSERT-\gexec без вердикта; DELETE-зона после MERGE идёт уже при
     `on` снова — `\if` там безопасен.

4. **Исполнимость «двух statement'ов» (B1.2) в stdin.** Да: два подряд `DELETE`
   в true-ветке `\if` — обычный psql. Per-entity mode — **SQL-предикатом**
   (`tmp3_build.mode`), не вложенным `\if` per-table (вложенный `\if` по
   результату запроса без `\gset` **не** сделать). План это подразумевает
   («два statement'а»), но **не выписывает** SQL — дыра детализации, не
   синтаксиса.

5. **Замок.** Сейчас `:131-133` запрещает любую строку `\if :partial_rebuild`.
   B1.3 верно требует сменить assert **тем же коммитом**. Иначе выкат не
   пройдёт оффлайн-замок ещё до scp.

---

## Ответы Q2–Q5

Ниже — ответы аудита (в v1 плана стоят как открытые вопросы §8). Каждый
предикат привязан к живому якорю.

### Q2 — count-equivalence для partial (B2.4 → :1470-1478)

**Ответ:** для `mode='full'` оставить текущий предикат :1470-1478.
Для `mode='partial'` текущее `в_корпусе <> собрано` (**блокер**, b1 атака 1b.1)
заменить на **ожидаемый count, посчитанный ДО DELETE** (после записи old уже
нет).

Предусловие формулы плана `|old| − |G∩old| + |new\old|`:
`gone_expand ∩ new_full = ∅` в том же такте (удалённый ключ не вставляется
снова). Если пересечение непусто — добавить `+|G∩new|` или проверять
множеством, не count.

**SQL (ожидание до записи, рядом с ent_counts :189-207):**

```sql
-- G = gone_expand (B3); old = search_corpus сущности; new = tmp3_corpus
CREATE OR REPLACE TABLE tmp3_merge_partial_expect AS
SELECT b.tbl AS src_table,
       (SELECT count(*)::BIGINT FROM search_corpus c WHERE c.src_table = b.tbl)
         - (SELECT count(*)::BIGINT FROM gone_expand g
            WHERE g.src_table = b.tbl
              AND EXISTS (SELECT 1 FROM search_corpus c
                          WHERE c.src_table = g.src_table
                            AND c.row_key = g.row_key))
         + (SELECT count(*)::BIGINT FROM tmp3_corpus t
            WHERE t.src_table = b.tbl
              AND NOT EXISTS (SELECT 1 FROM search_corpus c
                              WHERE c.src_table = t.src_table
                                AND c.row_key = t.row_key))
         AS expect
FROM tmp3_build b
WHERE b.mode = 'partial';
```

**Постчек (замена/сужение :1470-1478):**

```sql
SELECT CASE WHEN count(*) > 0 THEN error(
  'corpus_merge: после переноса разошлось число строк у сущностей: '
  || string_agg(src_table || ' (' || в_корпусе || ' против ' || ожидалось || ')', ', ')
) END
FROM (
  -- full: как сейчас
  SELECT t.src_table,
         (SELECT count(*) FROM search_corpus c WHERE c.src_table = t.src_table) AS в_корпусе,
         count(*)::BIGINT AS ожидалось
  FROM tmp3_corpus t
  WHERE EXISTS (SELECT 1 FROM tmp3_build b
                WHERE b.tbl = t.src_table AND b.mode = 'full')
  GROUP BY t.src_table
  UNION ALL
  -- partial: expect из снапшота
  SELECT e.src_table,
         (SELECT count(*) FROM search_corpus c WHERE c.src_table = e.src_table),
         e.expect
  FROM tmp3_merge_partial_expect e
) x
WHERE в_корпусе <> ожидалось;
```

Дополнительный set-witness (рекомендуется в тот же B2, не вместо count):
`EXISTS gone_expand-ключ ещё в корпусе` → STOP; `tmp3`-ключ отсутствует → STOP.

### Q3 — пустой partial-стейдж без маркеров (B2.1 → :117-121)

**Ответ: STOP.** Пустой `tmp3_corpus` у сущности из `tmp3_build` без свежих
`deleted_gone` = сбой сборки / ложный rebuild, не delete-only.
Легитимный delete-only: `mode='partial'` ∧ ∃ свежий `op='deleted_gone'`.

**Предикат замены :117-121:**

```sql
SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: сущности собрались пустыми, перенос отменён: '
                  || string_agg(tbl, ', ')) END
FROM (
  SELECT s.tbl
  FROM tmp3_build s
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = s.tbl)
    AND NOT (
      s.mode = 'partial'
      AND EXISTS (
        SELECT 1 FROM search_changed_rows k
        WHERE k.src_table = s.tbl
          AND k.op = 'deleted_gone'
          AND epoch(k.ts)::BIGINT
                > coalesce((SELECT v FROM search_quality
                            WHERE k = 'corpus_built_ts' LIMIT 1), 0)::BIGINT
      )
    )
);
```

Окно свежести — то же, что rehash (`:1024-1026`) / план B3.1.

### Q4 — orphan-путь при mixed mode (:577-582, :620-625, die_unexplained :997-998)

**Ответ:** свидетель full-сущностей **остаётся как сейчас** (витринный orphan →
`tmp3_merge_deleted_delta_rows` → `key_deleted_delta`). Для `mode='partial'`
orphan **не** является множеством DELETE и **не** должен entity-wide снимать
строки из «снесло бы» / unexplained, пока DELETE идёт по маркерам (иначе
PASS гварда + мусор в корпусе, или STOP гварда при пустом marker-DELETE — b1
атака 1a.4).

**Предикат сужения наполнения `key_deleted_delta` (:620-625):**

```sql
CREATE OR REPLACE TABLE tmp3_merge_key_deleted_delta AS
SELECT c.src_table, c.было, c.стало, count(d.row_key)::BIGINT AS уйдёт
FROM tmp3_merge_collapse_cand c
INNER JOIN tmp3_merge_deleted_delta_rows d ON d.src_table = c.src_table
WHERE EXISTS (SELECT 1 FROM tmp3_build b
              WHERE b.tbl = c.src_table AND b.mode = 'full')  -- NEW
  AND NOT EXISTS (SELECT 1 FROM tmp3_merge_transport_defect t
                  WHERE t.src_table = c.src_table)
GROUP BY 1, 2, 3;
```

**Предикат die_unexplained (:997-998) — UNION по mode (B2.2):**

```sql
-- вместо одного NOT EXISTS key_deleted_delta на всю сущность:
AND NOT (
  (EXISTS (SELECT 1 FROM tmp3_build b
           WHERE b.tbl = o.src_table AND b.mode = 'full')
   AND EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta d
               WHERE d.src_table = o.src_table))
  OR
  (EXISTS (SELECT 1 FROM tmp3_build b
           WHERE b.tbl = o.src_table AND b.mode = 'partial')
   AND EXISTS (SELECT 1 FROM gone_expand g
               WHERE g.src_table = o.src_table
                 AND g.row_key = o.row_key))  -- row-level, не entity-wide!
)
```

Важно: сегодня `:997-998` исключает **всю** сущность. Для partial нужен
**row-level** gone_expand (B3), иначе одна gone-строка «объяснит» всех соседей.

### Q5 — агрегация 10%-гварда per-mode (:688-709 + wave :209-214)

**Ответ:** в числитель «уйдёт» входят только ключи, которые **реально удалит**
B1: unmatched full-сущностей (текущий anti-join-мир) ∪ gone∪expand
partial-сущностей. Знаменатель — `count(*) FROM search_corpus` (как сейчас).
Partial-соседи ∉ gone **не** считаются уйдёт.

**Предикат числителя (замена подзапроса :692-709):**

```sql
SELECT count(*) AS уйдёт FROM (
  -- full: текущий unmatched минус те же объяснения
  SELECT u.src_table, u.row_key
  FROM tmp3_merge_unmatched u
  WHERE EXISTS (SELECT 1 FROM tmp3_build b
                WHERE b.tbl = u.src_table AND b.mode = 'full')
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_form k WHERE k.src_table = u.src_table)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_rewrite_wave k WHERE k.src_table = u.src_table)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse k WHERE k.src_table = u.src_table)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta k WHERE k.src_table = u.src_table)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_shrink s WHERE s.src_table = u.src_table)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_repost_delta r WHERE r.src_table = u.src_table)
  UNION
  -- partial: только gone∪expand (множество B3)
  SELECT g.src_table, g.row_key
  FROM gone_expand g
  WHERE EXISTS (SELECT 1 FROM tmp3_build b
                WHERE b.tbl = g.src_table AND b.mode = 'partial')
) del;
```

**rewrite-wave (:209-214):** считать только `mode='full'` (иначе урезанный
стейдж + ошибочное «под partial» даёт rewrite-семантику — b1 1b.2):

```sql
FROM tmp3_merge_ent_counts e
WHERE EXISTS (SELECT 1 FROM tmp3_build b WHERE b.tbl = e.src_table AND b.mode = 'full')
  AND было > 0 AND стало > 0 AND стало >= было
  AND (было - matched_exact)::DOUBLE / было >= 0.9
  AND abs(стало - было)::DOUBLE / было <= 0.05;
```

**Обязательное следствие (нет в v1 B2):** тот же scope — на `p_merge_unmatched`
(:226+) / `ent_guard` (:343-361) / гейт «частичная потеря» (:637-653), иначе
10% зелёный, а 0.1% STOPит раньше.

---

## Атаки

1. **Инверсия ветки `\if`.** Если перепутать true/false (`\if` на 0 уйдёт в
   partial-тело) или положить anti-join в true-ветку — при первом
   `partial_rebuild=1` wipe соседей с emb (:1371-1374). Защита: замок B1.3
   («между `\else` и `\endif` стоит прежний anti-join») + B7 flip=0 (else
   горячий). При `partial_rebuild=0` инверсия true↔else не проявляется, пока
   flip не включён — ложный PASS B7.

2. **Entity без строки mode при `partial_rebuild=1`.** L4(б) build
   (`corpus_build.sql:1541-1546`) ловит NULL/не full|partial в `tmp3_build`.
   Атака: ключ в `tmp3_corpus`, но сущность **нет** в `tmp3_build` (рассинхрон)
   или DELETE фильтрует `INNER JOIN tmp3_build` и entity выпадает из обоих
   списков → gone не удалится (недоудаление), anti-join не сработает. Merge
   сторож A при flip=1 **не** требует mode=full. Нужен STOP в merge:
   `EXISTS tmp3_corpus.src_table ∉ tmp3_build.tbl` или `mode IS NULL`.

3. **Parent full / child partial — кто удаляет детей?** B1.2: «parent/child mix
   закрыт: каждый по своему mode» — **ложное закрытие**. Anti-join шапки
   (:1371, ограниченный full-списком) **не трогает** дочернюю ТЧ. Partial-ребёнок
   удаляет только свой gone∪expand (B3). Маркер `deleted_gone` на Ref родителя
   без fanout в таблицу ребёнка → сироты ТЧ в корпусе с живым emb. Build тянет
   детей lag-родителя в стейдж (`corpus_build.sql:1504-1505`, :1535-1536), но
   это про **включение в rebuild**, не про DELETE детей при gone родителя.
   **Правка в план:** явно (i) expand B3 кросс-табличный по `search_tables.parent`,
   или (ii) при gone родителя форсировать child `mode='full'` / маркер `*`,
   или (iii) STOP если parent gone ∧ child partial ∧ дети живы в корпусе.

4. **Empty-build при delete-only с фальшивым маркером.** Предикат Q3 пропускает
   пустой стейдж при любом свежем `deleted_gone`. Атака: маркер с
   патологией `*` / битым key_text (B3.2 → expand пусто) + пустой `tmp3_corpus`
   → empty-build PASS, DELETE ничего не удаляет, count-eq partial «0=0»,
   сущность «пересобрана» пустотой при живых соседях. **STOP-дополнение:**
   empty∧partial → требовать `|gone_expand(e)| > 0` (после B3, до записи), не
   только ∃ маркер; стык с pathology/hash_kill.

5. **Сужение unmatched ломает shrink/repost для full в mixed-такте.**
   `tmp3_merge_shrink` (:371-374) и collapse/repost-цепочка (:423+) питаются от
   `ent_guard` ← count(`tmp3_merge_unmatched`). Если unmatched PREPARE
   «заодно» ограничить только partial-логикой или INNER JOIN mode без
   сохранения full-пути — full-сущность в том же такте потеряет shrink/repost
   свидетелей → ложный STOP «частичная потеря» (:637) или «снесло бы» (:688)
   на честной убыли 1С. **Правка:** unmatched строить как сейчас для
   `mode='full'`; для `mode='partial'` либо не наполнять unmatched соседями,
   либо наполнять только ключами ∈ gone_expand (тот же scope, что DELETE).

6. *(доп.)* **B2 без сужения `ent_guard` 0.1% (:637-653).** Даже при верном
   10%-гварде (Q5) partial с несокращённым unmatched стопнется раньше на
   «частичная потеря» (b1 1b.2 явно называет оба порога). В v1 B2 пункта нет.

7. *(доп.)* **`die_unmatched` (:954-960) без сужения.** B2.2 правит только
   `die_unexplained`. `unmatched_kill` останется ≈ всем emb∉стейджа → причина
   в quality/`векторов_умрёт`-алиас (B3.6) путается; при ошибке в формуле
   unexplained (entity-wide vs row-level) гейт loss (:1089-1109) STOPит до
   записи. Стык 1b↔1c (b1 пробел 10) в v1 назван, но die_unmatched не перечислен
   в B2.

---

## Вектора

**Инвариант:** при `partial_rebuild=1` и корректном mode ни одна строка с живым
`emb`, чей `(src_table,row_key) ∉ gone∪expand`, не удаляется из `search_corpus`.

| Путь | Строки | При partial_rebuild=1 + верном B1 | При баге mode / инверсии |
|---|---|---|---|
| Anti-join DELETE | :1371-1374 | Только в `\else` или для `mode='full'` | Wipe всех ключей стейдж-сущности ∉ tmp3 — **emb уходит со строкой** |
| Partial DELETE gone∪expand | (нет в коде; B1+B3) | Только G | При пустом G — недоудаление; при слишком широком expand — лишние emb |
| Sources-orphan | :1381-1382 | Вне mode (не трогать) | Не про mode |
| `SET emb=NULL` | :1311-1317 | Только ключи пачки tmp3 | Вне дельты не трогает |
| die_unexplained / loss | :975-1011, :1089-1109 | STOP **до** MERGE (:1290), если unexplained не вычтен G | Ложный STOP (соседи) или PASS+wipe если DELETE уже после гейта с неверным scope |
| rehash_gate | :1118-1162 | STOP до записи; строка жива | Не DELETE |
| count-eq | :1470-1478 | **После** записи — поздно для emb; только детект | При partial без Q2 — вечный STOP после успешного wipe/merge |

**Где STOP до записи (порядок файла):** empty-build :117 → сторож A :123 → …
→ unmatched/гварды :223-709 → **vec-budget / unexplained / loss :890-1110** →
**rehash :1131-1162** → только потом MERGE :1290 → DELETE :1371.
Святое для emb-соседей держится **формой DELETE** (B1) + тем, что budget
STOPит до DELETE, если unexplained считает соседей смертью (B2.2+B3). Баг
«mode=full всем при flip=1» + anti-join = wipe **после** прошедшего budget
(budget видит тот же anti-join-мир как unmatched_kill — при полном стейдже
full-сущности budget зелёный, wipe «честный» для full; при partial-стейдже и
забытом ветвлении DELETE budget должен STOP **до** wipe, если unexplained не
объяснён — иначе окно: budget PASS при entity-wide deleted_delta-исключении +
anti-join wipe).

Доказательство «баг mode не удаляет живой emb вне G» **не** следует из текущего
кода (ветвления нет). Следует только из спецификации B1.2: partial-ветка =
`DELETE … WHERE (src_table,row_key) IN gone_expand`, без `NOT EXISTS tmp3_corpus`.

---

## Внесено / упущено из b1

Сверка `fullb2-audit-b1.md` пробелы 1–10 и атаки → v1.

| # b1 | Тема | В v1? |
|---|---|---|
| П1 | формула count-eq partial | **частично:** B2.4 + **Q2 открыт** (формулы SQL нет) |
| П2 | владелец gone∪expand 1a↔1c | **внесено:** B1.2→«множество B3»; B3; атомарность B7 «B1+B2+B3+… одним md5»; запрет 1c≺1a |
| П3 | судьба orphan deleted_delta | **частично:** якорь в шапке; **Q4 открыт** |
| П4 | empty-build delete-only | **частично:** B2.1; **Q3 открыт** (ответ аудита: STOP без маркеров) |
| П5 | конфликт `\if` vs замок | **внесено:** B1.3 + B6.1 |
| П6 | mixed parent/child, число DELETE | **частично:** «два statement'а»; «mix закрыт» **без механизма детей** |
| П7 | оффлайн-фикстуры до scp / связь этап 4/6a0 | **частично:** 0.1–0.3, B6, B7; **нет** явного списка фикстур partial (empty+gone-only, mixed, anti-join выключен→соседи emb) |
| П8 | замеры 1a/1b без flip | **упущено:** B7 = только flip=0 / mode=full всем; partial-семантика без flip не принимается |
| П9 | устаревшие :1250+ / :588 | **внесено:** шапка :1371-1374, :597-604 |
| П10 | стык unmatched ↔ die_unmatched | **частично:** B2.2 про die_unexplained; **die_unmatched :954-960 и ent_guard :637 не в B2** |

| Атака b1 | В v1? |
|---|---|
| 1a.1 wipe при partial | покрыто B1.1–1.2 |
| 1a.2 мир ключей без expand | покрыто связкой B1+B3, атомарность |
| 1a.3 mixed parent/child | **упущено** по существу (см. атака 3) |
| 1a.4 два gone-пути | **Q4**, не решено |
| 1a.5 SKIP / else байт-в-байт | B1.1, B2.5, B7 |
| 1a.6 flip без этапа 4 | порядок в «ДАЛЬШЕ» канона-предка; в B v1 слабо (0.2 про дельту A, не про p_doc) |
| 1b.1 count-eq STOP | B2.4 / Q2 |
| 1b.2 unmatched / wave / 0.1% | B2.3 / Q5; **0.1% ent_guard упущен** |
| 1b.3 empty-build | B2.1 / Q3 |
| 1b.4 глобальный 10% | B2.3 / Q5 |
| 1b.5 SKIP при сужении через JOIN mode | B2.5 + B7; риск NULL-mode края не расписан |
| 1b.6 die_unmatched сосед 1c | B2.2 только unexplained |

**Упущено списком (для правки v1):**
1. Закрыть Q2–Q5 дословными предикатами (блок выше) или вложить ответы в B2.
2. Механизм parent gone → child cleanup (не декларация «mix закрыт»).
3. B2: сузить `ent_guard` / гейт `:637-653` тем же scope, что unmatched.
4. B2: сузить `die_unmatched` (:954-960) и/или явно сказать «unexpected только
   из unexplained; unmatched_kill — диагностика».
5. Empty∧partial → `|gone_expand|>0`, не только ∃ маркер (анти-фальшивка).
6. Merge-STOP: всякая `tmp3_corpus`-сущность имеет строку `tmp3_build.mode`.
7. Оффлайн-фикстуры partial в B6/B7 (без flip): соседи emb бит-в-байт; count-eq;
   empty+gone-only; mixed full/partial; shrink/repost full в mixed.
8. Явное: правки unmatched/wave/guards при `partial_rebuild=0` не меняют
   кардинальности STOP-классов (allowlist B7) — включая план запроса/NULL mode.

---

## Вердикт: план P1-части **не готов**

Семантика цели B1/B2 согласована с кодом и с b1; якоря шапки верны; `\if`+0/1
исполним в psql stdin рядом с `ON_ERROR_STOP`. Блокеры детализации/выката:

1. Q2–Q5 в §8 всё ещё открыты — без вписанных предикатов исполнитель снова
   получит wipe или STOP на :1470 / :688 / :637.
2. Parent/child не закрыт механизмом.
3. `ent_guard` 0.1% и `die_unmatched` вне текста B2.
4. Фикстуры/приёмка partial без flip отсутствуют (только B7 full).

### Правки дословно (внести в v1)

**B1.2 — заменить предложение про parent/child на:**
> Parent `full` / child `partial`: anti-join шапки детей не трогает. Удаление
> детей при `deleted_gone` родителя — либо (A) `gone_expand` включает строки
> child-таблиц через `search_tables.parent` + fanout_cap, либо (B) build
> форсирует child `mode='full'` при gone/full-маркере родителя, либо (C)
> merge STOP: parent ∈ gone_markers ∧ child.mode=partial ∧ ∃ child-строки в
> корпусе с префиксом ключа родителя. Без A/B/C — пакет B не выкатывать.

**B1 — добавить пункт 5:**
> До DELETE: `SELECT CASE WHEN EXISTS (SELECT 1 FROM tmp3_corpus t
> WHERE NOT EXISTS (SELECT 1 FROM tmp3_build b WHERE b.tbl=t.src_table
> AND b.mode IN ('full','partial'))) THEN error('…mode отсутствует') END;`

**B2.1 — после «Partial без маркеров… STOP (Q3)» дописать:**
> Q3 = STOP. Delete-only легитимен только при mode=partial ∧ ∃ свежий
> deleted_gone ∧ \|gone_expand(e)\|>0 (после B3, до записи). Предикат
> empty-build — как в аудите P1 §Q3.

**B2.2 — дописать:**
> die_unmatched (:954-960) для mode=partial считает только ключи ∈ gone_expand
> (или не входит в векторов_умрёт; unexpected ≡ unexplained EXCEPT …).
> NOT EXISTS key_deleted_delta при partial заменяется row-level gone_expand;
> при full — entity-wide как сейчас. Orphan→key_deleted_delta только mode=full
> (Q4 = да для full-свидетеля).

**B2.3 — дописать:**
> Тот же scope уйдёт, что DELETE: формула числителя 10% — аудит P1 §Q5.
> rewrite-wave только mode=full. **Также** `tmp3_merge_ent_guard` и гейт
> «частичная потеря» :637-653 сузить: для partial уйдёт := \|gone_expand\|
> (минус объяснения), не count(unmatched-соседей).

**B2.4 — заменить «точная формула — Q2» на:**
> Q2 = expect до DELETE: \|old\|−\|G∩old\|+\|new\old\| при G∩new=∅;
> постчек — аудит P1 §Q2; full — :1470-1478 без изменений.

**B2 — новый подпункт 6:**
> Наполнение `tmp3_merge_unmatched`: mode=full — текущие PREPARE :226-333;
> mode=partial — только ключи ∈ gone_expand (или пусто + уйдёт из G в
> ent_guard). Запрещено сужать full-путь так, чтобы shrink/repost
> (:371-374, :597-618) потеряли свидетелей в mixed-такте.

**B6/B7 — добавить фикстуры (оффлайн, без flip):**
> (i) partial стейдж + anti-join выключен → count emb соседей бит-в-байт;
> (ii) count-eq partial по expect; (iii) empty+gone-only PASS;
> (iv) empty без маркеров STOP; (v) mixed full+partial: shrink/repost full
> зелёные; (vi) parent gone / child partial → срабатывает выбранный A/B/C.

**§8 — Q2–Q5:** пометить «отвечены аудитом P1; вписать в B2» или удалить как
открытые.

После этих правок — повторная линза P1 (или accept оркестратором) до SQL-детализации.
